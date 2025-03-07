import os
import sqlite3
import datetime
from datetime import date
import calendar
import locale

try:
    locale.setlocale(locale.LC_TIME, 'ru_RU.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_TIME, 'Russian_Russia.1251')
    except:
        pass  # Если не удалось установить русскую локаль, оставляем по умолчанию

# Создаем класс для работы с базой данных
class FinanceTracker:
    def __init__(self):
        # Используем текущую директорию запуска скрипта
        script_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.path.join(script_dir, "finance_tracker")
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
            
        self.db_path = os.path.join(data_dir, "finance.db")
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.setup_database()
    
    def setup_database(self):
        # Создаем таблицу счетов
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            balance REAL DEFAULT 0,
            type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        # Создаем таблицу операций
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            category TEXT,
            transaction_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            transaction_type TEXT NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        )
        ''')
        
        # Создаем таблицу для регулярных платежей
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS recurring_payments (
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            description TEXT NOT NULL,
            category TEXT,
            payment_day INTEGER NOT NULL,
            active INTEGER DEFAULT 1,
            last_processed DATE,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        )
        ''')
        
        # Создаем таблицу для запланированных платежей
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS planned_payments (
            id INTEGER PRIMARY KEY,
            account_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            description TEXT NOT NULL,
            category TEXT,
            planned_date DATE,
            completed INTEGER DEFAULT 0,
            FOREIGN KEY (account_id) REFERENCES accounts (id)
        )
        ''')
        
        # Создаем таблицу для переводов между счетами
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY,
            from_account_id INTEGER NOT NULL,
            to_account_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            description TEXT,
            transfer_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (from_account_id) REFERENCES accounts (id),
            FOREIGN KEY (to_account_id) REFERENCES accounts (id)
        )
        ''')

        # Создаем таблицу категорий
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS expense_categories (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Создаем таблицу категорий доходов
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS income_categories (
            id INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        ''')

        # Проверяем, есть ли уже категории расходов, если нет - добавляем стандартные
        self.cursor.execute("SELECT COUNT(*) FROM expense_categories")
        if self.cursor.fetchone()[0] == 0:
            default_expense_categories = [
                "Продукты", "Кафе и рестораны", "Транспорт", "Жилье", 
                "Коммунальные услуги", "Связь и интернет", "Одежда", 
                "Развлечения", "Здоровье", "Образование", "Другое"
            ]
            for category in default_expense_categories:
                self.cursor.execute("INSERT INTO expense_categories (name) VALUES (?)", (category,))
        
        # Проверяем, есть ли уже категории доходов, если нет - добавляем стандартные
        self.cursor.execute("SELECT COUNT(*) FROM income_categories")
        if self.cursor.fetchone()[0] == 0:
            default_income_categories = [
                "Зарплата", "Подработка", "Проценты по вкладам", "Дивиденды", 
                "Подарки", "Возврат долгов", "Продажи", "Другое"
            ]
            for category in default_income_categories:
                self.cursor.execute("INSERT INTO income_categories (name) VALUES (?)", (category,))
        
        self.conn.commit()
    
    def close(self):
        self.conn.close()
    
    # Методы для работы со счетами
    def create_account(self, name, type, initial_balance=0):
        try:
            self.cursor.execute(
                "INSERT INTO accounts (name, balance, type) VALUES (?, ?, ?)",
                (name, initial_balance, type)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    
    def get_accounts(self):
        self.cursor.execute("SELECT id, name, balance, type FROM accounts")
        return self.cursor.fetchall()
    
    def get_account_by_id(self, account_id):
        self.cursor.execute("SELECT id, name, balance, type FROM accounts WHERE id = ?", (account_id,))
        return self.cursor.fetchone()
    
    def update_account(self, account_id, name=None, account_type=None):
        current = self.get_account_by_id(account_id)
        if not current:
            return False
        
        new_name = name if name else current[1]
        new_type = account_type if account_type else current[3]
        
        try:
            self.cursor.execute(
                "UPDATE accounts SET name = ?, type = ? WHERE id = ?",
                (new_name, new_type, account_id)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    
    def delete_account(self, account_id):
        # Проверяем, есть ли операции, связанные с этим счетом
        self.cursor.execute("SELECT COUNT(*) FROM transactions WHERE account_id = ?", (account_id,))
        if self.cursor.fetchone()[0] > 0:
            return False, "Нельзя удалить счёт с операциями"
        
        self.cursor.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        self.conn.commit()
        return True, "Счёт успешно удалён"
    
    # Методы для операций дохода/расхода
    def add_income(self, account_id, amount, description="", category=""):
        account = self.get_account_by_id(account_id)
        if not account:
            return False, "Счёт не найден"
        
        try:
            # Добавляем транзакцию
            self.cursor.execute(
                "INSERT INTO transactions (account_id, amount, description, category, transaction_type) VALUES (?, ?, ?, ?, ?)",
                (account_id, amount, description, category, "income")
            )
            
            # Обновляем баланс счета
            new_balance = account[2] + amount
            self.cursor.execute(
                "UPDATE accounts SET balance = ? WHERE id = ?",
                (new_balance, account_id)
            )
            
            self.conn.commit()
            return True, "Доход успешно добавлен"
        except Exception as e:
            return False, str(e)
    
    def add_expense(self, account_id, amount, description="", category=""):
        account = self.get_account_by_id(account_id)
        if not account:
            return False, "Счёт не найден"
        
        if account[2] < amount:
            return False, "Недостаточно средств"
        
        try:
            # Добавляем транзакцию (расход как отрицательное число)
            self.cursor.execute(
                "INSERT INTO transactions (account_id, amount, description, category, transaction_type) VALUES (?, ?, ?, ?, ?)",
                (account_id, -amount, description, category, "expense")
            )
            
            # Обновляем баланс счета
            new_balance = account[2] - amount
            self.cursor.execute(
                "UPDATE accounts SET balance = ? WHERE id = ?",
                (new_balance, account_id)
            )
            
            self.conn.commit()
            return True, "Расход успешно добавлен"
        except Exception as e:
            return False, str(e)
        
    def get_transaction_by_id(self, transaction_id):
        self.cursor.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,))
        return self.cursor.fetchone()

    def delete_transaction(self, transaction_id):
        # Находим транзакцию
        transaction = self.get_transaction_by_id(transaction_id)
        if not transaction:
            return False, "Операция не найдена"
        
        account_id = transaction[1]
        amount = transaction[2]
        
        # Получаем данные счета
        account = self.get_account_by_id(account_id)
        if not account:
            return False, "Счёт не найден"
        
        try:
            # Отменяем влияние транзакции на баланс счета
            new_balance = account[2] - amount  # Вычитаем сумму операции (для дохода она положительная, для расхода - отрицательная)
            self.cursor.execute(
                "UPDATE accounts SET balance = ? WHERE id = ?",
                (new_balance, account_id)
            )
            
            # Удаляем транзакцию
            self.cursor.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
            
            self.conn.commit()
            return True, "Операция успешно удалена"
        except Exception as e:
            return False, str(e)

    def update_transaction(self, transaction_id, amount=None, description=None, category=None):
        # Находим транзакцию
        transaction = self.get_transaction_by_id(transaction_id)
        if not transaction:
            return False, "Операция не найдена"
        
        account_id = transaction[1]
        old_amount = transaction[2]
        
        # Если новая сумма не указана, используем старую
        new_amount = amount if amount is not None else old_amount
        
        # Получаем данные счета
        account = self.get_account_by_id(account_id)
        if not account:
            return False, "Счёт не найден"
        
        try:
            # Обновляем баланс счета
            amount_diff = new_amount - old_amount
            new_balance = account[2] + amount_diff
            
            # Проверка на отрицательный баланс для расходов
            if transaction[6] == "expense" and amount is not None:
                # Для расхода, amount в БД отрицательный, а на входе в функцию положительный
                if account[2] + old_amount < amount:  # old_amount < 0, поэтому +old_amount
                    return False, "Недостаточно средств"
                # Корректируем new_amount, чтобы для расхода было отрицательное значение
                if new_amount > 0:
                    new_amount = -new_amount
            
            # Обновляем баланс
            self.cursor.execute(
                "UPDATE accounts SET balance = ? WHERE id = ?",
                (new_balance, account_id)
            )
            
            # Обновляем транзакцию
            new_description = description if description is not None else transaction[3]
            new_category = category if category is not None else transaction[4]
            
            self.cursor.execute(
                """UPDATE transactions 
                SET amount = ?, description = ?, category = ?
                WHERE id = ?""",
                (new_amount, new_description, new_category, transaction_id)
            )
            
            self.conn.commit()
            return True, "Операция успешно обновлена"
        except Exception as e:
            return False, str(e)
    
    # Методы для перевода между счетами
    def transfer_money(self, from_account_id, to_account_id, amount, description=""):
        if from_account_id == to_account_id:
            return False, "Нельзя перевести деньги на тот же счёт"
        
        from_account = self.get_account_by_id(from_account_id)
        to_account = self.get_account_by_id(to_account_id)
        
        if not from_account or not to_account:
            return False, "Один из счетов не найден"
        
        if from_account[2] < amount:
            return False, "Недостаточно средств для перевода"
        
        try:
            # Создаем запись о переводе
            self.cursor.execute(
                "INSERT INTO transfers (from_account_id, to_account_id, amount, description) VALUES (?, ?, ?, ?)",
                (from_account_id, to_account_id, amount, description)
            )
            
            # Обновляем балансы обоих счетов
            new_from_balance = from_account[2] - amount
            new_to_balance = to_account[2] + amount
            
            self.cursor.execute(
                "UPDATE accounts SET balance = ? WHERE id = ?",
                (new_from_balance, from_account_id)
            )
            
            self.cursor.execute(
                "UPDATE accounts SET balance = ? WHERE id = ?",
                (new_to_balance, to_account_id)
            )
            
            self.conn.commit()
            return True, "Перевод успешно выполнен"
        except Exception as e:
            return False, str(e)
        
    def get_transfers(self, account_id=None, start_date=None, end_date=None, limit=None):
        query = """
            SELECT t.id, t.from_account_id, fa.name as from_name, t.to_account_id, 
                ta.name as to_name, t.amount, t.description, t.transfer_date
            FROM transfers t
            JOIN accounts fa ON t.from_account_id = fa.id
            JOIN accounts ta ON t.to_account_id = ta.id
            WHERE 1=1
        """
        params = []
        
        if account_id:
            query += " AND (t.from_account_id = ? OR t.to_account_id = ?)"
            params.extend([account_id, account_id])
        
        if start_date:
            query += " AND DATE(t.transfer_date) >= DATE(?)"
            params.append(start_date)
        
        if end_date:
            query += " AND DATE(t.transfer_date) <= DATE(?)"
            params.append(end_date)
        
        query += " ORDER BY t.transfer_date DESC"
        
        if limit is not None:
            query += f" LIMIT {int(limit)}"
        
        self.cursor.execute(query, params)
        return self.cursor.fetchall()
    
    # Методы для работы с регулярными платежами
    def add_recurring_payment(self, account_id, amount, description, payment_day, category=""):
        if payment_day < 1 or payment_day > 31:
            return False, "День платежа должен быть от 1 до 31"
        
        account = self.get_account_by_id(account_id)
        if not account:
            return False, "Счёт не найден"
        
        try:
            self.cursor.execute(
                "INSERT INTO recurring_payments (account_id, amount, description, category, payment_day) VALUES (?, ?, ?, ?, ?)",
                (account_id, amount, description, category, payment_day)
            )
            self.conn.commit()
            return True, "Регулярный платеж добавлен"
        except Exception as e:
            return False, str(e)
    
    def process_recurring_payments(self):
        self.print_header("ОБРАБОТКА АВТОПЛАТЕЖЕЙ")
        today = date.today()
        day_of_month = today.day
        
        # Получаем все активные регулярные платежи, у которых день платежа равен текущему
        self.cursor.execute(
            "SELECT id, account_id, amount, description, category FROM recurring_payments WHERE payment_day = ? AND active = 1",
            (day_of_month,)
        )
        payments = self.cursor.fetchall()
        
        results = []
        for payment in payments:
            payment_id, account_id, amount, description, category = payment
            
            # Проверяем, не был ли платеж уже обработан в этом месяце
            self.cursor.execute(
                "SELECT last_processed FROM recurring_payments WHERE id = ?",
                (payment_id,)
            )
            last_processed = self.cursor.fetchone()[0]
            
            if last_processed:
                last_processed_date = datetime.datetime.strptime(last_processed, "%Y-%m-%d").date()
                if last_processed_date.month == today.month and last_processed_date.year == today.year:
                    # Платеж уже обработан в этом месяце
                    continue
            
            # Выполняем платеж
            account = self.get_account_by_id(account_id)
            if account[2] < amount:
                results.append((False, f"{description}: Недостаточно средств"))
                continue
            
            # Добавляем транзакцию
            self.cursor.execute(
                "INSERT INTO transactions (account_id, amount, description, category, transaction_type) VALUES (?, ?, ?, ?, ?)",
                (account_id, -amount, f"Авто: {description}", category, "expense")
            )
            
            # Обновляем баланс счета
            new_balance = account[2] - amount
            self.cursor.execute(
                "UPDATE accounts SET balance = ? WHERE id = ?",
                (new_balance, account_id)
            )
            
            # Обновляем дату последней обработки платежа
            self.cursor.execute(
                "UPDATE recurring_payments SET last_processed = ? WHERE id = ?",
                (today.strftime("%Y-%m-%d"), payment_id)
            )
            
            results.append((True, f"{description}: Автоплатеж выполнен"))
        
        self.conn.commit()
        return results
    
    def get_recurring_payments(self):
        self.cursor.execute("""
            SELECT r.id, r.account_id, a.name, r.amount, r.description, r.category, r.payment_day, r.active 
            FROM recurring_payments r
            JOIN accounts a ON r.account_id = a.id
        """)
        return self.cursor.fetchall()
    
    def update_recurring_payment(self, payment_id, account_id=None, amount=None, description=None, payment_day=None, active=None):
        self.cursor.execute(
            "SELECT account_id, amount, description, payment_day, active FROM recurring_payments WHERE id = ?",
            (payment_id,)
        )
        payment = self.cursor.fetchone()
        
        if not payment:
            return False, "Платеж не найден"
        
        new_account_id = account_id if account_id is not None else payment[0]
        new_amount = amount if amount is not None else payment[1]
        new_description = description if description is not None else payment[2]
        new_payment_day = payment_day if payment_day is not None else payment[3]
        new_active = active if active is not None else payment[4]
        
        if new_payment_day < 1 or new_payment_day > 31:
            return False, "День платежа должен быть от 1 до 31"
        
        try:
            self.cursor.execute(
                """UPDATE recurring_payments 
                SET account_id = ?, amount = ?, description = ?, payment_day = ?, active = ?
                WHERE id = ?""",
                (new_account_id, new_amount, new_description, new_payment_day, new_active, payment_id)
            )
            self.conn.commit()
            return True, "Регулярный платеж обновлен"
        except Exception as e:
            return False, str(e)
    
    def delete_recurring_payment(self, payment_id):
        self.cursor.execute("DELETE FROM recurring_payments WHERE id = ?", (payment_id,))
        self.conn.commit()
        return True, "Регулярный платеж удален"
    
    # Методы для запланированных платежей
    def add_planned_payment(self, account_id, amount, description, planned_date, category=""):
        account = self.get_account_by_id(account_id)
        if not account:
            return False, "Счёт не найден"
        
        try:
            self.cursor.execute(
                "INSERT INTO planned_payments (account_id, amount, description, category, planned_date) VALUES (?, ?, ?, ?, ?)",
                (account_id, amount, description, category, planned_date)
            )
            self.conn.commit()
            return True, "Запланированный платеж добавлен"
        except Exception as e:
            return False, str(e)
    
    def get_planned_payments(self, only_active=True):
        query = """
            SELECT p.id, p.account_id, a.name, p.amount, p.description, p.category, p.planned_date, p.completed 
            FROM planned_payments p
            JOIN accounts a ON p.account_id = a.id
        """
        
        if only_active:
            query += " WHERE p.completed = 0"
            
        self.cursor.execute(query)
        original_data = self.cursor.fetchall()
        
        # Если нужно только активные, создаем "виртуальные" ID
        if only_active and original_data:
            virtual_data = []
            for idx, row in enumerate(original_data, 1):
                # Сохраняем оригинальный ID в кортеже на первом месте, но возвращаем виртуальный ID
                # Добавим оригинальный ID как последний элемент для внутреннего использования
                real_id = row[0]
                virtual_data.append((idx,) + row[1:] + (real_id,))
            return virtual_data
        
        return original_data
    
    def update_planned_payment(self, payment_id, account_id=None, amount=None, description=None, category=None, planned_date=None):
        """Обновляет запланированный платеж"""
        # Пробуем получить реальный ID из расширенного кортежа
        if isinstance(payment_id, int):
            self.cursor.execute(
                "SELECT id FROM planned_payments WHERE id = ? AND completed = 0",
                (payment_id,)
            )
            result = self.cursor.fetchone()
            
            if not result:
                # Может быть, это виртуальный ID? Пробуем получить все активные платежи
                payments = self.get_planned_payments(True)
                
                # Ищем платеж с нужным виртуальным ID
                real_id = None
                for p in payments:
                    if p[0] == payment_id:
                        real_id = p[-1]  # Последний элемент - реальный ID
                        break
                        
                if real_id is None:
                    return False, "Платеж не найден"
                    
                payment_id = real_id
        
        self.cursor.execute(
            "SELECT account_id, amount, description, category, planned_date, completed FROM planned_payments WHERE id = ?",
            (payment_id,)
        )
        payment = self.cursor.fetchone()
        
        if not payment:
            return False, "Платеж не найден"
        
        if payment[5] == 1:
            return False, "Нельзя редактировать выполненный платеж"
        
        new_account_id = account_id if account_id is not None else payment[0]
        new_amount = amount if amount is not None else payment[1]
        new_description = description if description is not None else payment[2]
        new_category = category if category is not None else payment[3]
        new_planned_date = planned_date if planned_date is not None else payment[4]
        
        try:
            self.cursor.execute(
                """UPDATE planned_payments 
                SET account_id = ?, amount = ?, description = ?, category = ?, planned_date = ?
                WHERE id = ?""",
                (new_account_id, new_amount, new_description, new_category, new_planned_date, payment_id)
            )
            self.conn.commit()
            return True, "Запланированный платеж обновлен"
        except Exception as e:
            return False, str(e)
    
    def execute_planned_payment(self, payment_id):
        # Пробуем получить реальный ID из расширенного кортежа
        if isinstance(payment_id, int):
            self.cursor.execute(
                "SELECT id FROM planned_payments WHERE id = ? AND completed = 0",
                (payment_id,)
            )
            result = self.cursor.fetchone()
            
            if not result:
                # Может быть, это виртуальный ID? Пробуем получить все активные платежи
                payments = self.get_planned_payments(True)
                
                # Ищем платеж с нужным виртуальным ID
                real_id = None
                for p in payments:
                    if p[0] == payment_id:
                        real_id = p[-1]  # Последний элемент - реальный ID
                        break
                        
                if real_id is None:
                    return False, "Платеж не найден"
                    
                payment_id = real_id
        
        self.cursor.execute(
            "SELECT account_id, amount, description, category, completed FROM planned_payments WHERE id = ?",
            (payment_id,)
        )
        payment = self.cursor.fetchone()
        
        if not payment:
            return False, "Платеж не найден"
        
        if payment[4] == 1:
            return False, "Платеж уже выполнен"
        
        account_id, amount, description, category, _ = payment
        account = self.get_account_by_id(account_id)
        
        if account[2] < amount:
            return False, "Недостаточно средств"
        
        try:
            # Добавляем транзакцию
            self.cursor.execute(
                "INSERT INTO transactions (account_id, amount, description, category, transaction_type) VALUES (?, ?, ?, ?, ?)",
                (account_id, -amount, description, category, "expense")
            )
            
            # Обновляем баланс счета
            new_balance = account[2] - amount
            self.cursor.execute(
                "UPDATE accounts SET balance = ? WHERE id = ?",
                (new_balance, account_id)
            )
            
            # Отмечаем платеж как выполненный
            self.cursor.execute(
                "UPDATE planned_payments SET completed = 1 WHERE id = ?",
                (payment_id,)
            )
            
            self.conn.commit()
            return True, "Запланированный платеж выполнен"
        except Exception as e:
            return False, str(e)
    
    def delete_planned_payment(self, payment_id):
        # Пробуем получить реальный ID из расширенного кортежа
        if isinstance(payment_id, int):
            self.cursor.execute(
                "SELECT id FROM planned_payments WHERE id = ? AND completed = 0",
                (payment_id,)
            )
            result = self.cursor.fetchone()
            
            if not result:
                # Может быть, это виртуальный ID? Пробуем получить все активные платежи
                payments = self.get_planned_payments(True)
                
                # Ищем платеж с нужным виртуальным ID
                real_id = None
                for p in payments:
                    if p[0] == payment_id:
                        real_id = p[-1]  # Последний элемент - реальный ID
                        break
                        
                if real_id is None:
                    return False, "Платеж не найден"
                    
                payment_id = real_id
                    
        self.cursor.execute("DELETE FROM planned_payments WHERE id = ?", (payment_id,))
        self.conn.commit()
        return True, "Запланированный платеж удален"
    
    # Методы для получения статистики/отчетов
    def get_transactions(self, account_id=None, start_date=None, end_date=None, transaction_type=None, limit=None):
        query = """
            SELECT t.id, t.account_id, a.name, t.amount, t.description, t.category, t.transaction_date, t.transaction_type
            FROM transactions t
            JOIN accounts a ON t.account_id = a.id
            WHERE 1=1
        """
        params = []
        
        if account_id:
            query += " AND t.account_id = ?"
            params.append(account_id)
        
        if start_date:
            query += " AND DATE(t.transaction_date) >= DATE(?)"
            params.append(start_date)
        
        if end_date:
            query += " AND DATE(t.transaction_date) <= DATE(?)"
            params.append(end_date)
        
        if transaction_type:
            query += " AND t.transaction_type = ?"
            params.append(transaction_type)
        
        query += " ORDER BY t.transaction_date DESC"
        
        if limit is not None:
            query += f" LIMIT {int(limit)}"
        
        self.cursor.execute(query, params)
        return self.cursor.fetchall()
    
    def get_category_summary(self, start_date=None, end_date=None, transaction_type=None):
        """
        Получает статистику по категориям для определенного типа транзакций
        (expense, income) или для всех, если тип не указан
        """
        # Если тип не указан, используем все типы
        if transaction_type is None:
            query = """
                SELECT category, transaction_type, SUM(amount) as total
                FROM transactions
                WHERE 1=1
            """
        else:
            query = """
                SELECT category, transaction_type, SUM(amount) as total
                FROM transactions
                WHERE transaction_type = ?
            """
        
        params = []
        if transaction_type is not None:
            params.append(transaction_type)
        
        if start_date:
            query += " AND DATE(transaction_date) >= DATE(?)"
            params.append(start_date)
        
        if end_date:
            query += " AND DATE(transaction_date) <= DATE(?)"
            params.append(end_date)
        
        query += " GROUP BY category, transaction_type ORDER BY total ASC"
        
        self.cursor.execute(query, params)
        return self.cursor.fetchall()
    
    def get_monthly_summary(self, year=None):
        if not year:
            year = datetime.datetime.now().year
            
        results = []
        for month in range(1, 13):
            start_date = f"{year}-{month:02d}-01"
            last_day = calendar.monthrange(year, month)[1]
            end_date = f"{year}-{month:02d}-{last_day:02d}"
            
            # Получаем доходы за месяц
            self.cursor.execute(
                "SELECT SUM(amount) FROM transactions WHERE transaction_type = 'income' AND DATE(transaction_date) BETWEEN ? AND ?",
                (start_date, end_date)
            )
            income = self.cursor.fetchone()[0] or 0
            
            # Получаем расходы за месяц
            self.cursor.execute(
                "SELECT SUM(amount) FROM transactions WHERE transaction_type = 'expense' AND DATE(transaction_date) BETWEEN ? AND ?",
                (start_date, end_date)
            )
            expense = self.cursor.fetchone()[0] or 0
            
            month_name = calendar.month_name[month]
            results.append((month_name, income, expense, income + expense))
            
        return results
    
    def get_day_comparison(self):
        """Сравнивает расходы и доходы за сегодня с расходами и доходами за вчера"""
        today = datetime.date.today()
        yesterday = today - datetime.timedelta(days=1)
        
        # Получаем расходы за сегодня
        self.cursor.execute(
            "SELECT SUM(amount) FROM transactions WHERE transaction_type = 'expense' " +
            "AND DATE(transaction_date) = DATE(?)",
            (today.strftime("%Y-%m-%d"),)
        )
        today_expenses = abs(self.cursor.fetchone()[0] or 0)
        
        # Получаем расходы за вчера
        self.cursor.execute(
            "SELECT SUM(amount) FROM transactions WHERE transaction_type = 'expense' " +
            "AND DATE(transaction_date) = DATE(?)",
            (yesterday.strftime("%Y-%m-%d"),)
        )
        yesterday_expenses = abs(self.cursor.fetchone()[0] or 0)
        
        # Получаем доходы за сегодня
        self.cursor.execute(
            "SELECT SUM(amount) FROM transactions WHERE transaction_type = 'income' " +
            "AND DATE(transaction_date) = DATE(?)",
            (today.strftime("%Y-%m-%d"),)
        )
        today_income = self.cursor.fetchone()[0] or 0
        
        # Получаем доходы за вчера
        self.cursor.execute(
            "SELECT SUM(amount) FROM transactions WHERE transaction_type = 'income' " +
            "AND DATE(transaction_date) = DATE(?)",
            (yesterday.strftime("%Y-%m-%d"),)
        )
        yesterday_income = self.cursor.fetchone()[0] or 0
        
        # Вычисляем процентное изменение для расходов
        if yesterday_expenses == 0:
            expense_percent_change = 100 if today_expenses > 0 else 0
        else:
            expense_percent_change = ((today_expenses - yesterday_expenses) / yesterday_expenses) * 100
        
        # Вычисляем процентное изменение для доходов
        if yesterday_income == 0:
            income_percent_change = 100 if today_income > 0 else 0
        else:
            income_percent_change = ((today_income - yesterday_income) / yesterday_income) * 100
        
        # Вычисляем отношение расход/доход
        today_ratio = (today_expenses / today_income) * 100 if today_income > 0 else float('inf')
        yesterday_ratio = (yesterday_expenses / yesterday_income) * 100 if yesterday_income > 0 else float('inf')
        
        # Если обе величины конечны, вычисляем изменение
        if today_ratio != float('inf') and yesterday_ratio != float('inf'):
            ratio_percent_change = ((today_ratio - yesterday_ratio) / yesterday_ratio) * 100
        else:
            ratio_percent_change = 0
        
        return {
            'today_date': today.strftime("%d.%m.%Y"),
            'today_expenses': today_expenses,
            'today_income': today_income,
            'today_ratio': today_ratio if today_ratio != float('inf') else None,
            'yesterday_date': yesterday.strftime("%d.%m.%Y"),
            'yesterday_expenses': yesterday_expenses,
            'yesterday_income': yesterday_income,
            'yesterday_ratio': yesterday_ratio if yesterday_ratio != float('inf') else None,
            'expense_percent_change': expense_percent_change,
            'income_percent_change': income_percent_change,
            'ratio_percent_change': ratio_percent_change
        }
    
    def get_week_comparison(self):
        """Сравнивает расходы и доходы за текущую неделю с предыдущей"""
        today = datetime.date.today()
        
        # Определяем начало и конец текущей недели (понедельник-воскресенье)
        current_week_start = today - datetime.timedelta(days=today.weekday())
        current_week_end = today
        
        # Определяем начало и конец предыдущей недели
        prev_week_start = current_week_start - datetime.timedelta(days=7)
        prev_week_end = current_week_start - datetime.timedelta(days=1)
        
        # Получаем расходы за текущую неделю
        self.cursor.execute(
            "SELECT SUM(amount) FROM transactions WHERE transaction_type = 'expense' " +
            "AND DATE(transaction_date) BETWEEN DATE(?) AND DATE(?)",
            (current_week_start.strftime("%Y-%m-%d"), current_week_end.strftime("%Y-%m-%d"))
        )
        current_week_expenses = abs(self.cursor.fetchone()[0] or 0)
        
        # Получаем расходы за предыдущую неделю
        self.cursor.execute(
            "SELECT SUM(amount) FROM transactions WHERE transaction_type = 'expense' " +
            "AND DATE(transaction_date) BETWEEN DATE(?) AND DATE(?)",
            (prev_week_start.strftime("%Y-%m-%d"), prev_week_end.strftime("%Y-%m-%d"))
        )
        prev_week_expenses = abs(self.cursor.fetchone()[0] or 0)
        
        # Получаем доходы за текущую неделю
        self.cursor.execute(
            "SELECT SUM(amount) FROM transactions WHERE transaction_type = 'income' " +
            "AND DATE(transaction_date) BETWEEN DATE(?) AND DATE(?)",
            (current_week_start.strftime("%Y-%m-%d"), current_week_end.strftime("%Y-%m-%d"))
        )
        current_week_income = self.cursor.fetchone()[0] or 0
        
        # Получаем доходы за предыдущую неделю
        self.cursor.execute(
            "SELECT SUM(amount) FROM transactions WHERE transaction_type = 'income' " +
            "AND DATE(transaction_date) BETWEEN DATE(?) AND DATE(?)",
            (prev_week_start.strftime("%Y-%m-%d"), prev_week_end.strftime("%Y-%m-%d"))
        )
        prev_week_income = self.cursor.fetchone()[0] or 0
        
        # Вычисляем процентное изменение для расходов
        if prev_week_expenses == 0:
            expense_percent_change = 100 if current_week_expenses > 0 else 0
        else:
            expense_percent_change = ((current_week_expenses - prev_week_expenses) / prev_week_expenses) * 100
        
        # Вычисляем процентное изменение для доходов
        if prev_week_income == 0:
            income_percent_change = 100 if current_week_income > 0 else 0
        else:
            income_percent_change = ((current_week_income - prev_week_income) / prev_week_income) * 100
        
        # Вычисляем отношение расход/доход
        current_week_ratio = (current_week_expenses / current_week_income) * 100 if current_week_income > 0 else float('inf')
        prev_week_ratio = (prev_week_expenses / prev_week_income) * 100 if prev_week_income > 0 else float('inf')
        
        # Если обе величины конечны, вычисляем изменение
        if current_week_ratio != float('inf') and prev_week_ratio != float('inf'):
            ratio_percent_change = ((current_week_ratio - prev_week_ratio) / prev_week_ratio) * 100
        else:
            ratio_percent_change = 0
        
        return {
            'current_week_start': current_week_start.strftime("%d.%m.%Y"),
            'current_week_end': current_week_end.strftime("%d.%m.%Y"),
            'current_week_expenses': current_week_expenses,
            'current_week_income': current_week_income,
            'current_week_ratio': current_week_ratio if current_week_ratio != float('inf') else None,
            'prev_week_start': prev_week_start.strftime("%d.%m.%Y"),
            'prev_week_end': prev_week_end.strftime("%d.%m.%Y"),
            'prev_week_expenses': prev_week_expenses,
            'prev_week_income': prev_week_income,
            'prev_week_ratio': prev_week_ratio if prev_week_ratio != float('inf') else None,
            'expense_percent_change': expense_percent_change,
            'income_percent_change': income_percent_change,
            'ratio_percent_change': ratio_percent_change
        }
    
    def get_month_comparison(self):
        """Сравнивает расходы и доходы за текущий месяц с предыдущим"""
        today = datetime.date.today()
        
        # Определяем начало текущего месяца
        current_month_start = today.replace(day=1)
        current_month_end = today
        
        # Определяем начало и конец предыдущего месяца
        if current_month_start.month == 1:
            prev_month_start = current_month_start.replace(year=current_month_start.year-1, month=12, day=1)
        else:
            prev_month_start = current_month_start.replace(month=current_month_start.month-1, day=1)
        
        # Последний день предыдущего месяца
        prev_month_end = current_month_start - datetime.timedelta(days=1)
        
        # Получаем расходы за текущий месяц
        self.cursor.execute(
            "SELECT SUM(amount) FROM transactions WHERE transaction_type = 'expense' " +
            "AND DATE(transaction_date) BETWEEN DATE(?) AND DATE(?)",
            (current_month_start.strftime("%Y-%m-%d"), current_month_end.strftime("%Y-%m-%d"))
        )
        current_month_expenses = abs(self.cursor.fetchone()[0] or 0)
        
        # Получаем расходы за предыдущий месяц
        self.cursor.execute(
            "SELECT SUM(amount) FROM transactions WHERE transaction_type = 'expense' " +
            "AND DATE(transaction_date) BETWEEN DATE(?) AND DATE(?)",
            (prev_month_start.strftime("%Y-%m-%d"), prev_month_end.strftime("%Y-%m-%d"))
        )
        prev_month_expenses = abs(self.cursor.fetchone()[0] or 0)
        
        # Получаем доходы за текущий месяц
        self.cursor.execute(
            "SELECT SUM(amount) FROM transactions WHERE transaction_type = 'income' " +
            "AND DATE(transaction_date) BETWEEN DATE(?) AND DATE(?)",
            (current_month_start.strftime("%Y-%m-%d"), current_month_end.strftime("%Y-%m-%d"))
        )
        current_month_income = self.cursor.fetchone()[0] or 0
        
        # Получаем доходы за предыдущий месяц
        self.cursor.execute(
            "SELECT SUM(amount) FROM transactions WHERE transaction_type = 'income' " +
            "AND DATE(transaction_date) BETWEEN DATE(?) AND DATE(?)",
            (prev_month_start.strftime("%Y-%m-%d"), prev_month_end.strftime("%Y-%m-%d"))
        )
        prev_month_income = self.cursor.fetchone()[0] or 0
        
        # Вычисляем процентное изменение для расходов
        if prev_month_expenses == 0:
            expense_percent_change = 100 if current_month_expenses > 0 else 0
        else:
            expense_percent_change = ((current_month_expenses - prev_month_expenses) / prev_month_expenses) * 100
        
        # Вычисляем процентное изменение для доходов
        if prev_month_income == 0:
            income_percent_change = 100 if current_month_income > 0 else 0
        else:
            income_percent_change = ((current_month_income - prev_month_income) / prev_month_income) * 100
        
        # Вычисляем отношение расход/доход
        current_month_ratio = (current_month_expenses / current_month_income) * 100 if current_month_income > 0 else float('inf')
        prev_month_ratio = (prev_month_expenses / prev_month_income) * 100 if prev_month_income > 0 else float('inf')
        
        # Если обе величины конечны, вычисляем изменение
        if current_month_ratio != float('inf') and prev_month_ratio != float('inf'):
            ratio_percent_change = ((current_month_ratio - prev_month_ratio) / prev_month_ratio) * 100
        else:
            ratio_percent_change = 0
        
        return {
            'current_month': current_month_start.strftime("%B %Y"),
            'current_month_expenses': current_month_expenses,
            'current_month_income': current_month_income,
            'current_month_ratio': current_month_ratio if current_month_ratio != float('inf') else None,
            'prev_month': prev_month_start.strftime("%B %Y"),
            'prev_month_expenses': prev_month_expenses,
            'prev_month_income': prev_month_income,
            'prev_month_ratio': prev_month_ratio if prev_month_ratio != float('inf') else None,
            'expense_percent_change': expense_percent_change,
            'income_percent_change': income_percent_change,
            'ratio_percent_change': ratio_percent_change
        }
    
    # Методы для работы с категориями
    def get_categories(self):
        self.cursor.execute("SELECT id, name FROM expense_categories ORDER BY name")
        return self.cursor.fetchall()

    def add_category(self, name):
        try:
            self.cursor.execute(
                "INSERT INTO expense_categories (name) VALUES (?)",
                (name,)
            )
            self.conn.commit()
            return True, "Категория успешно добавлена"
        except sqlite3.IntegrityError:
            return False, "Категория с таким названием уже существует"
        except Exception as e:
            return False, str(e)

    def update_category(self, category_id, new_name):
        try:
            self.cursor.execute(
                "UPDATE expense_categories SET name = ? WHERE id = ?",
                (new_name, category_id)
            )
            self.conn.commit()
            return True, "Категория успешно обновлена"
        except sqlite3.IntegrityError:
            return False, "Категория с таким названием уже существует"
        except Exception as e:
            return False, str(e)

    def delete_category(self, category_id):
        try:
            self.cursor.execute("DELETE FROM expense_categories WHERE id = ?", (category_id,))
            self.conn.commit()
            return True, "Категория успешно удалена"
        except Exception as e:
            return False, str(e)

    def get_category_by_id(self, category_id):
        self.cursor.execute("SELECT id, name FROM expense_categories WHERE id = ?", (category_id,))
        return self.cursor.fetchone()

    def get_category_by_name(self, name):
        self.cursor.execute("SELECT id, name FROM expense_categories WHERE name = ?", (name,))
        return self.cursor.fetchone()
    
    # Методы для работы с категориями доходов
    def get_income_categories(self):
        self.cursor.execute("SELECT id, name FROM income_categories ORDER BY name")
        return self.cursor.fetchall()

    def add_income_category(self, name):
        try:
            self.cursor.execute(
                "INSERT INTO income_categories (name) VALUES (?)",
                (name,)
            )
            self.conn.commit()
            return True, "Категория дохода успешно добавлена"
        except sqlite3.IntegrityError:
            return False, "Категория с таким названием уже существует"
        except Exception as e:
            return False, str(e)

    def update_income_category(self, category_id, new_name):
        try:
            self.cursor.execute(
                "UPDATE income_categories SET name = ? WHERE id = ?",
                (new_name, category_id)
            )
            self.conn.commit()
            return True, "Категория дохода успешно обновлена"
        except sqlite3.IntegrityError:
            return False, "Категория с таким названием уже существует"
        except Exception as e:
            return False, str(e)

    def delete_income_category(self, category_id):
        try:
            self.cursor.execute("DELETE FROM income_categories WHERE id = ?", (category_id,))
            self.conn.commit()
            return True, "Категория дохода успешно удалена"
        except Exception as e:
            return False, str(e)

    def get_income_category_by_id(self, category_id):
        self.cursor.execute("SELECT id, name FROM income_categories WHERE id = ?", (category_id,))
        return self.cursor.fetchone()

    def get_income_category_by_name(self, name):
        self.cursor.execute("SELECT id, name FROM income_categories WHERE name = ?", (name,))
        return self.cursor.fetchone()


# Класс для управления интерфейсом
class ConsoleUI:
    def __init__(self):
        self.tracker = FinanceTracker()
        self.running = True
    
    def clear_screen(self):
        os.system('clear' if os.name == 'posix' else 'cls')
    
    def print_header(self, title):
        self.clear_screen()
        width = 50
        print("=" * width)
        print(f"✨ {title.center(width - 4)} ✨")
        print("=" * width)
    
    def print_message(self, message, success=True):
        prefix = "✅" if success else "❌"
        print(f"\n{prefix} {message}")
        input("\n👉 Нажмите Enter, чтобы продолжить...")
    
    def input_number(self, prompt, min_value=None, max_value=None):
        while True:
            try:
                value = float(input(prompt))
                if min_value is not None and value < min_value:
                    print(f"Значение должно быть не меньше {min_value}")
                    continue
                if max_value is not None and value > max_value:
                    print(f"Значение должно быть не больше {max_value}")
                    continue
                return value
            except ValueError:
                print("Пожалуйста, введите число")
    
    def input_date(self, prompt):
        while True:
            try:
                date_str = input(prompt + " (ДД.ММ.ГГ): ")
                day, month, year = date_str.split('.')
                # Конвертируем двузначный год в четырехзначный
                if len(year) == 2:
                    year = "20" + year
                # Форматируем дату в формат ГГГГ-ММ-ДД для хранения в БД
                return datetime.datetime.strptime(f"{year}-{month}-{day}", "%Y-%m-%d").strftime("%Y-%m-%d")
            except ValueError:
                print("Неверный формат даты. Используйте ДД.ММ.ГГ")
    
    def select_account(self, prompt="Выберите счёт:"):
        accounts = self.tracker.get_accounts()
        if not accounts:
            print("Нет доступных счетов")
            return None
        
        print(prompt)
        for i, account in enumerate(accounts, 1):
            print(f"{i}. {account[1]} ({account[2]} ₽) - {account[3]}")
        print("0. Назад")  # Добавляем опцию возврата
        
        choice = self.input_number("Введите номер счёта: ", 0, len(accounts))  # Разрешаем 0
        if choice == 0:  # Проверяем, выбрал ли пользователь опцию выхода
            return 0
        return accounts[int(choice) - 1][0]  # Возвращаем ID выбранного счёта
        
    def main_menu(self):
        while self.running:
            self.print_header("ФИНАНСОВЫЙ ТРЕКЕР")
            print("1. 💼 Управление счетами")
            print("2. 💰 Доходы и расходы")
            print("3. 🔄 Переводы")
            print("4. 🔔 Регулярные платежи")
            print("5. 📅 Запланированные платежи")
            print("6. 📊 Отчёты и статистика")
            print("7. 🏷️ Управление категориями") 
            print("0. 🚪 Выход")
            
            choice = self.input_number("Выберите пункт меню: ", 0, 7)  # Обновляем диапазон
            
            if choice == 1:
                self.accounts_menu()
            elif choice == 2:
                self.transactions_menu()
            elif choice == 3:
                self.transfer_menu()
            elif choice == 4:
                self.recurring_payments_menu()
            elif choice == 5:
                self.planned_payments_menu()
            elif choice == 6:
                self.reports_menu()
            elif choice == 7:
                self.categories_menu()  # Вызываем новый метод
            elif choice == 0:
                self.running = False
                self.tracker.close()
                print("👋 До свидания!")
    
    def accounts_menu(self):
        while True:
            self.print_header("УПРАВЛЕНИЕ СЧЕТАМИ")
            print("1. 👁️ Просмотр всех счетов")
            print("2. ➕ Создать новый счёт")
            print("3. ✏️ Редактировать счёт")
            print("4. ❌ Удалить счёт")
            print("0. 🔙 Назад")
            
            choice = self.input_number("Выберите пункт меню: ", 0, 4)
            
            if choice == 1:
                self.show_accounts()
            elif choice == 2:
                self.create_account()
            elif choice == 3:
                self.edit_account()
            elif choice == 4:
                self.delete_account()
            elif choice == 0:
                break
    
    def show_accounts(self):
        self.print_header("СПИСОК СЧЕТОВ")
        accounts = self.tracker.get_accounts()
        
        if not accounts:
            print("📭 У вас пока нет счетов")
        else:
            total_balance = 0
            for account in accounts:
                total_balance += account[2]
                account_type_emoji = self.get_account_type_emoji(account[3])
                print(f"{account_type_emoji} {account[1]} ({account[3]}): {account[2]} ₽")
            
            print("\n" + "-" * 30)
            print(f"💵 Общий баланс: {total_balance} ₽")
        
        input("\n👉 Нажмите Enter, чтобы продолжить...")

    def get_account_type_emoji(self, account_type):
        emoji_map = {
            "Наличные": "💵",
            "Дебетовая карта": "💳",
            "Кредитная карта": "💳",
            "Сберегательный счёт": "🏦",
            "Инвестиции": "📈",
            "Другое": "🔄"
        }
        return emoji_map.get(account_type, "💰")
    
    def create_account(self):
        self.print_header("СОЗДАНИЕ СЧЁТА")
        name = input("Введите название счёта: ")
        
        print("\nТипы счетов:")
        print("1. Наличные")
        print("2. Дебетовая карта")
        print("3. Кредитная карта")
        print("4. Сберегательный счёт")
        print("5. Инвестиции")
        print("6. Другое")
        
        type_choice = self.input_number("Выберите тип счёта: ", 1, 6)
        account_types = ["Наличные", "Дебетовая карта", "Кредитная карта", "Сберегательный счёт", "Инвестиции", "Другое"]
        account_type = account_types[int(type_choice) - 1]
        
        initial_balance = self.input_number("Введите начальный баланс: ", 0)
        
        success = self.tracker.create_account(name, account_type, initial_balance)
        
        if success:
            self.print_message(f"Счёт '{name}' успешно создан")
        else:
            self.print_message(f"Счёт с названием '{name}' уже существует", False)
    
    def edit_account(self):
        self.print_header("РЕДАКТИРОВАНИЕ СЧЁТА")
        account_id = self.select_account()
        
        if not account_id:
            return
        
        account = self.tracker.get_account_by_id(account_id)
        print(f"Редактирование счёта: {account[1]} ({account[3]})")
        
        new_name = input(f"Введите новое название (или оставьте пустым для '{account[1]}'): ")
        if not new_name:
            new_name = account[1]
        
        print("\nТипы счетов:")
        print("1. Наличные")
        print("2. Дебетовая карта")
        print("3. Кредитная карта")
        print("4. Сберегательный счёт")
        print("5. Инвестиции")
        print("6. Другое")
        print(f"Текущий тип: {account[3]}")
        
        type_choice = input("Выберите тип счёта (или оставьте пустым, чтобы не менять): ")
        
        if type_choice:
            account_types = ["Наличные", "Дебетовая карта", "Кредитная карта", "Сберегательный счёт", "Инвестиции", "Другое"]
            try:
                account_type = account_types[int(type_choice) - 1]
            except (ValueError, IndexError):
                self.print_message("Неверный выбор типа счёта", False)
                return
        else:
            account_type = account[3]
        
        success = self.tracker.update_account(account_id, new_name, account_type)
        
        if success:
            self.print_message(f"Счёт успешно обновлен")
        else:
            self.print_message("Ошибка при обновлении счёта", False)
    
    def delete_account(self):
        self.print_header("УДАЛЕНИЕ СЧЁТА")
        account_id = self.select_account()
        
        if not account_id:
            return
        
        account = self.tracker.get_account_by_id(account_id)
        if not self.input_yes_no(f"Вы уверены, что хотите удалить счёт '{account[1]}' с балансом {account[2]} ₽? (д/н): "):
            self.print_message("Удаление отменено")
            return
        
        success, message = self.tracker.delete_account(account_id)
        self.print_message(message, success)
    
    def transactions_menu(self):
        while True:
            self.print_header("ДОХОДЫ И РАСХОДЫ")
            print("1. 💸 Добавить доход")
            print("2. 💳 Добавить расход")
            print("3. 📋 Просмотр операций")
            print("4. ✏️ Редактировать операцию")
            print("5. ❌ Удалить операцию")
            print("0. 🔙 Назад")
            
            choice = self.input_number("Выберите пункт меню: ", 0, 5)
            
            if choice == 1:
                self.add_income()
            elif choice == 2:
                self.add_expense()
            elif choice == 3:
                self.show_transactions()
            elif choice == 4:
                self.edit_transaction()
            elif choice == 5:
                self.delete_transaction()
            elif choice == 0:
                break
    
    def add_income(self):
        self.print_header("ДОБАВЛЕНИЕ ДОХОДА")
        account_id = self.select_account("На какой счёт поступил доход:")
        
        if not account_id:
            return
        
        amount = self.input_number("Введите сумму дохода: ", 0.01)
        description = input("Введите описание: ")
        
        category = self.select_income_category("Выберите категорию дохода:")
        
        success, message = self.tracker.add_income(account_id, amount, description, category)
        self.print_message(message, success)

    def add_expense(self):
        self.print_header("ДОБАВЛЕНИЕ РАСХОДА")
        account_id = self.select_account("С какого счёта списать расход:")
        
        if not account_id:
            return
        
        amount = self.input_number("Введите сумму расхода: ", 0.01)
        description = input("Введите описание: ")
        
        category = self.select_expense_category("Выберите категорию расхода:")
        
        success, message = self.tracker.add_expense(account_id, amount, description, category)
        self.print_message(message, success)
    
    def show_transactions(self):
        self.print_header("ПРОСМОТР ОПЕРАЦИЙ")
        
        print("Фильтры:")
        print("1. Все операции")
        print("2. По счёту")
        print("3. По типу (доходы/расходы)")
        print("4. По периоду")
        print("5. Комбинированный фильтр")
        
        choice = self.input_number("Выберите фильтр: ", 1, 5)
        
        account_id = None
        start_date = None
        end_date = None
        transaction_type = None
        
        if choice == 2 or choice == 5:
            account_id = self.select_account()
            if not account_id and choice == 2:
                return
        
        if choice == 3 or choice == 5:
            print("\n1. Доходы")
            print("2. Расходы")
            type_choice = self.input_number("Выберите тип: ", 1, 2)
            transaction_type = "income" if type_choice == 1 else "expense"
        
        if choice == 4 or choice == 5:
            start_date = self.input_date("Введите начальную дату")
            end_date = self.input_date("Введите конечную дату")
        
        transactions = self.tracker.get_transactions(account_id, start_date, end_date, transaction_type)
        
        if not transactions:
            print("\nНет операций, соответствующих фильтрам")
            input("\nНажмите Enter, чтобы продолжить...")
            return
        
        self.print_header("СПИСОК ОПЕРАЦИЙ")
        
        for t in transactions:
            amount = t[3]
            sign = "+" if amount > 0 else ""
            emoji = "💰" if amount > 0 else "💸"
            category = f"[{t[5]}]" if t[5] else ""
            date = datetime.datetime.strptime(t[6], "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
            print(f"{date} | {t[2]} | {emoji} {sign}{amount} ₽ | {t[4]} {category}")
        
        input("\n👉 Нажмите Enter, чтобы продолжить...")

    def select_transaction(self):
        self.print_header("ВЫБОР ОПЕРАЦИИ")
        
        # Получаем список последних операций
        transactions = self.tracker.get_transactions(limit=10)
        
        if not transactions:
            self.print_message("Нет доступных операций", False)
            return None
        
        print("Последние операции:")
        for i, t in enumerate(transactions, 1):
            transaction_id, account_id, account_name, amount, description, category, date, transaction_type = t
            sign = "+" if amount > 0 else ""
            category_str = f"[{category}]" if category else ""
            formatted_date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
            print(f"{i}. {formatted_date} | {account_name} | {sign}{amount} ₽ | {description} {category_str}")
        
        print("\n0. Поиск по номеру ID")
        
        choice = self.input_number("Выберите операцию или введите 0 для поиска: ", 0, len(transactions))
        
        if choice == 0:
            transaction_id = self.input_number("Введите ID операции: ", 1)
            return transaction_id
        else:
            return transactions[int(choice) - 1][0]  # Возвращаем ID выбранной операции

    def edit_transaction(self):
        self.print_header("РЕДАКТИРОВАНИЕ ОПЕРАЦИИ")
        
        transaction_id = self.select_transaction()
        if not transaction_id:
            return
        
        # Получаем информацию о транзакции
        self.tracker.cursor.execute(
            "SELECT t.id, t.account_id, a.name, t.amount, t.description, t.category, t.transaction_date, t.transaction_type " +
            "FROM transactions t JOIN accounts a ON t.account_id = a.id " +
            "WHERE t.id = ?", (transaction_id,)
        )
        transaction = self.tracker.cursor.fetchone()
        
        if not transaction:
            self.print_message("Операция не найдена", False)
            return
        
        transaction_id, account_id, account_name, amount, description, category, date, transaction_type = transaction
        is_expense = transaction_type == "expense"
        
        # Отображаем текущие значения
        print(f"Редактирование операции #{transaction_id}")
        print(f"Счёт: {account_name}")
        print(f"Тип: {'Расход' if is_expense else 'Доход'}")
        print(f"Сумма: {abs(amount)} ₽")
        print(f"Описание: {description}")
        print(f"Категория: {category}")
        print(f"Дата: {datetime.datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')}")
        
        # Запрашиваем новые значения
        new_amount_str = input(f"Введите новую сумму (или оставьте пустым для {abs(amount)}): ")
        new_amount = float(new_amount_str) if new_amount_str else None
        
        new_description = input(f"Введите новое описание (или оставьте пустым): ")
        if not new_description:
            new_description = None
        
        # Заменяем запрос новой категории на выбор из списка соответствующего типа
        print("Текущая категория:", category if category else "Не указана")
        change_category = input("Изменить категорию? (д/н): ")
        if change_category.lower() in ['д', 'y', 'да', 'yes']:
            if is_expense:
                new_category = self.select_expense_category("Выберите новую категорию расхода:")
            else:
                new_category = self.select_income_category("Выберите новую категорию дохода:")
        else:
            new_category = None
        
        # Подтверждение
        print("\nНовые данные:")
        print(f"Сумма: {new_amount if new_amount is not None else abs(amount)} ₽")
        print(f"Описание: {new_description if new_description is not None else description}")
        print(f"Категория: {new_category if new_category is not None else category}")
        
        if not self.input_yes_no("\nСохранить изменения? (д/н): "):
            self.print_message("Редактирование отменено")
            return
        
        success, message = self.tracker.update_transaction(
            transaction_id, 
            amount=-new_amount if is_expense and new_amount is not None else new_amount,
            description=new_description,
            category=new_category
        )
        
        self.print_message(message, success)

    def delete_transaction(self):
        self.print_header("УДАЛЕНИЕ ОПЕРАЦИИ")
        
        transaction_id = self.select_transaction()
        if not transaction_id:
            return
        
        # Получаем информацию о транзакции
        self.tracker.cursor.execute(
            "SELECT t.id, a.name, t.amount, t.description, t.transaction_date " +
            "FROM transactions t JOIN accounts a ON t.account_id = a.id " +
            "WHERE t.id = ?", (transaction_id,)
        )
        transaction = self.tracker.cursor.fetchone()
        
        if not transaction:
            self.print_message("Операция не найдена", False)
            return
        
        transaction_id, account_name, amount, description, date = transaction
        
        # Отображаем информацию и запрашиваем подтверждение
        formatted_date = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
        sign = "+" if amount > 0 else ""
        print(f"Вы собираетесь удалить операцию:")
        print(f"{formatted_date} | {account_name} | {sign}{amount} ₽ | {description}")
        
        if not self.input_yes_no("\nВы уверены, что хотите удалить эту операцию? (д/н): "):
            self.print_message("Удаление отменено")
            return
        
        success, message = self.tracker.delete_transaction(transaction_id)
        self.print_message(message, success)
    
    def transfer_menu(self):
        while True:
            self.print_header("ПЕРЕВОДЫ МЕЖДУ СЧЕТАМИ")
            print("1. 💸 Сделать перевод")
            print("2. 📋 История переводов")
            print("0. 🔙 Назад")
            
            choice = self.input_number("Выберите пункт меню: ", 0, 2)
            
            if choice == 1:
                self.make_transfer()
            elif choice == 2:
                self.show_transfers_history()
            elif choice == 0:
                break

    def make_transfer(self):
        self.print_header("ПЕРЕВОД МЕЖДУ СЧЕТАМИ")
        
        accounts = self.tracker.get_accounts()
        if len(accounts) < 2:
            self.print_message("Для перевода нужно минимум два счёта", False)
            return
        
        # Передаем промпт с указанием возможности выйти
        from_account_id = self.select_account("Выберите счёт откуда:")
        if from_account_id == 0:  # Проверяем, был ли выбран выход
            return
        if not from_account_id:  # Если нет счетов
            return
        
        # Фильтруем список счетов, исключая выбранный
        filtered_accounts = [a for a in accounts if a[0] != from_account_id]
        
        print("\nВыберите счёт куда:")
        for i, account in enumerate(filtered_accounts, 1):
            print(f"{i}. {account[1]} ({account[2]} ₽) - {account[3]}")
        print("0. Назад")  # Добавляем опцию выхода
        
        choice = self.input_number("Введите номер счёта: ", 0, len(filtered_accounts))
        if choice == 0:  # Если выбран выход
            return
        
        to_account_id = filtered_accounts[int(choice) - 1][0]
        
        print("\nВведите сумму перевода (или 0 для отмены):")
        amount = self.input_number("Сумма: ", 0)
        if amount == 0:  # Если пользователь хочет отменить операцию
            self.print_message("Перевод отменен")
            return
            
        description = input("Введите описание (необязательно): ")
        
        success, message = self.tracker.transfer_money(from_account_id, to_account_id, amount, description)
        self.print_message(message, success)

    def show_transfers_history(self):
        self.print_header("ИСТОРИЯ ПЕРЕВОДОВ")
        
        print("Фильтры:")
        print("1. Все переводы")
        print("2. По счёту")
        print("3. По периоду")
        print("4. Комбинированный фильтр")
        
        choice = self.input_number("Выберите фильтр: ", 1, 4)
        
        account_id = None
        start_date = None
        end_date = None
        
        if choice == 2 or choice == 4:
            account_id = self.select_account("Выберите счёт для фильтрации:")
            if account_id == 0:  # Выбрана опция "Назад"
                return
        
        if choice == 3 or choice == 4:
            start_date = self.input_date("Введите начальную дату")
            end_date = self.input_date("Введите конечную дату")
        
        transfers = self.tracker.get_transfers(account_id, start_date, end_date)
        
        if not transfers:
            print("\nНет переводов, соответствующих фильтрам")
            input("\nНажмите Enter, чтобы продолжить...")
            return
        
        self.print_header("СПИСОК ПЕРЕВОДОВ")
        
        for t in transfers:
            transfer_id, from_id, from_name, to_id, to_name, amount, description, date = t
            date_formatted = datetime.datetime.strptime(date, "%Y-%m-%d %H:%M:%S").strftime("%d.%m.%Y %H:%M")
            desc = f" - {description}" if description else ""
            print(f"{date_formatted} | {from_name} 🔄 {to_name} | {amount} ₽{desc}")
        
        input("\n👉 Нажмите Enter, чтобы продолжить...")
    
    def recurring_payments_menu(self):
        while True:
            self.print_header("РЕГУЛЯРНЫЕ ПЛАТЕЖИ")
            print("1. 👁️ Просмотр всех регулярных платежей")
            print("2. ➕ Добавить регулярный платеж")
            print("3. ✏️ Изменить регулярный платеж")
            print("4. ❌ Удалить регулярный платеж")
            print("5. 🔄 Проверить и выполнить автоплатежи")
            print("0. 🔙 Назад")
            
            choice = self.input_number("Выберите пункт меню: ", 0, 5)
            
            if choice == 1:
                self.show_recurring_payments()
            elif choice == 2:
                self.add_recurring_payment()
            elif choice == 3:
                self.edit_recurring_payment()
            elif choice == 4:
                self.delete_recurring_payment()
            elif choice == 5:
                self.process_recurring_payments()
            elif choice == 0:
                break
    
    def show_recurring_payments(self):
        self.print_header("СПИСОК РЕГУЛЯРНЫХ ПЛАТЕЖЕЙ")
        payments = self.tracker.get_recurring_payments()
        
        if not payments:
            print("📭 У вас пока нет регулярных платежей")
        else:
            for p in payments:
                payment_id, account_id, account_name, amount, description, category, payment_day, active = p
                status = "✅ Активен" if active else "⛔ Отключен"
                category_str = f"[{category}]" if category else ""
                print(f"{payment_id}. 🔔 {description} {category_str} - {amount} ₽ с '{account_name}' (день: {payment_day}) - {status}")
        
        input("\n👉 Нажмите Enter, чтобы продолжить...")
    
    def add_recurring_payment(self):
        self.print_header("ДОБАВЛЕНИЕ РЕГУЛЯРНОГО ПЛАТЕЖА")
        account_id = self.select_account("С какого счёта будет списываться платеж:")
        
        if not account_id:
            return
        
        description = input("Введите название платежа (например, Подписка Netflix): ")
        amount = self.input_number("Введите сумму платежа: ", 0.01)
        payment_day = int(self.input_number("Введите день месяца для списания (1-31): ", 1, 31))
        
        # Список категорий расходов
        categories = [
            "Подписки", "Кредит", "Аренда", "Коммуналка", 
            "Связь", "Страховка", "Другое"
        ]
        
        print("\nКатегории:")
        for i, category in enumerate(categories, 1):
            print(f"{i}. {category}")
            
        cat_choice = input("Выберите категорию (или введите свою): ")
        
        try:
            category = categories[int(cat_choice) - 1]
        except (ValueError, IndexError):
            category = cat_choice
        
        success, message = self.tracker.add_recurring_payment(account_id, amount, description, payment_day, category)
        self.print_message(message, success)
    
    def edit_recurring_payment(self):
        self.print_header("ИЗМЕНЕНИЕ РЕГУЛЯРНОГО ПЛАТЕЖА")
        payments = self.tracker.get_recurring_payments()
        
        if not payments:
            self.print_message("У вас пока нет регулярных платежей", False)
            return
        
        print("Выберите платеж для редактирования:")
        for p in payments:
            payment_id, account_id, account_name, amount, description, category, payment_day, active = p
            status = "Активен" if active else "Отключен"
            print(f"{payment_id}. {description} - {amount} ₽ с '{account_name}' (день: {payment_day}) - {status}")
        
        payment_id = int(self.input_number("Введите ID платежа: ", 1))
        
        # Находим выбранный платеж
        selected_payment = None
        for p in payments:
            if p[0] == payment_id:
                selected_payment = p
                break
        
        if not selected_payment:
            self.print_message("Платеж не найден", False)
            return
        
        print(f"\nРедактирование платежа: {selected_payment[4]}")
        
        # Запрашиваем новые значения или оставляем старые
        new_account_id = None
        change_account = input("Изменить счёт? (д/н): ")
        if change_account.lower() in ['д', 'y', 'да', 'yes']:
            new_account_id = self.select_account()
        
        new_description = input(f"Введите новое название (или оставьте пустым для '{selected_payment[4]}'): ")
        if not new_description:
            new_description = None
        
        new_amount_str = input(f"Введите новую сумму (или оставьте пустым для '{selected_payment[3]}'): ")
        new_amount = float(new_amount_str) if new_amount_str else None
        
        new_day_str = input(f"Введите новый день месяца (или оставьте пустым для '{selected_payment[6]}'): ")
        new_day = int(new_day_str) if new_day_str else None
        
        print("\nСтатус платежа:")
        print("1. Активен")
        print("2. Отключен")
        status_choice = input(f"Выберите статус (или оставьте пустым для текущего): ")
        
        new_active = None
        if status_choice:
            new_active = 1 if status_choice == "1" else 0
        
        success, message = self.tracker.update_recurring_payment(
            payment_id, new_account_id, new_amount, new_description, new_day, new_active
        )
        
        self.print_message(message, success)
    
    def delete_recurring_payment(self):
        self.print_header("УДАЛЕНИЕ РЕГУЛЯРНОГО ПЛАТЕЖА")
        payments = self.tracker.get_recurring_payments()
        
        if not payments:
            self.print_message("У вас пока нет регулярных платежей", False)
            return
        
        print("Выберите платеж для удаления:")
        for p in payments:
            payment_id, account_id, account_name, amount, description, category, payment_day, active = p
            status = "Активен" if active else "Отключен"
            print(f"{payment_id}. {description} - {amount} ₽ с '{account_name}' (день: {payment_day}) - {status}")
        
        payment_id = int(self.input_number("Введите ID платежа: ", 1))
        
        if not self.input_yes_no(f"Вы уверены, что хотите удалить этот платеж? (д/н): "):
            self.print_message("Удаление отменено")
            return
        
        success, message = self.tracker.delete_recurring_payment(payment_id)
        self.print_message(message, success)
    
    def process_recurring_payments(self):
        self.print_header("ОБРАБОТКА АВТОПЛАТЕЖЕЙ")
        
        print("Проверка регулярных платежей на сегодня...")
        results = self.tracker.process_recurring_payments()
        
        if not results:
            print("\nНет платежей для обработки сегодня")
        else:
            for success, message in results:
                prefix = "✓" if success else "✗"
                print(f"{prefix} {message}")
        
        input("\nНажмите Enter, чтобы продолжить...")
    
    def planned_payments_menu(self):
        while True:
            self.print_header("ЗАПЛАНИРОВАННЫЕ ПЛАТЕЖИ")
            print("1. 👁️ Просмотр запланированных платежей")
            print("2. ➕ Добавить запланированный платеж")
            print("3. ✏️ Редактировать запланированный платеж") 
            print("4. ✅ Выполнить платеж")
            print("5. ❌ Удалить запланированный платеж")
            print("0. 🔙 Назад")
            
            choice = self.input_number("Выберите пункт меню: ", 0, 5) 
            
            if choice == 1:
                self.show_planned_payments()
            elif choice == 2:
                self.add_planned_payment()
            elif choice == 3:
                self.edit_planned_payment()
            elif choice == 4:
                self.execute_planned_payment()
            elif choice == 5:
                self.delete_planned_payment()
            elif choice == 0:
                break
    
    def show_planned_payments(self):
        self.print_header("СПИСОК ЗАПЛАНИРОВАННЫХ ПЛАТЕЖЕЙ")
        
        print("Отображать:")
        print("1. 📌 Только активные")
        print("2. 📋 Все, включая выполненные")
        
        choice = self.input_number("Выберите вариант: ", 1, 2)
        only_active = choice == 1
        
        payments = self.tracker.get_planned_payments(only_active)
        
        if not payments:
            print("📭 У вас пока нет запланированных платежей")
        else:
            for p in payments:
                if only_active:
                    # Если только активные, у нас есть доп. элемент - real_id
                    payment_id, account_id, account_name, amount, description, category, planned_date, completed, real_id = p
                else:
                    # Если все платежи, формат стандартный
                    payment_id, account_id, account_name, amount, description, category, planned_date, completed = p
                    
                status = "✅ Выполнен" if completed else "⏳ Ожидает"
                date = datetime.datetime.strptime(planned_date, "%Y-%m-%d").strftime("%d.%m.%y")
                category_str = f"[{category}]" if category else ""
                print(f"{payment_id}. 📅 {description} {category_str} - {amount} ₽ с '{account_name}' (дата: {date}) - {status}")
        
        input("\n👉 Нажмите Enter, чтобы продолжить...")
    
    def add_planned_payment(self):
        self.print_header("ДОБАВЛЕНИЕ ЗАПЛАНИРОВАННОГО ПЛАТЕЖА")
        account_id = self.select_account("С какого счёта будет списан платеж:")
        
        if not account_id:
            return
        
        description = input("Введите описание платежа: ")
        amount = self.input_number("Введите сумму платежа: ", 0.01)
        planned_date = self.input_date("Введите дату платежа")
        
        # Список категорий расходов
        categories = [
            "Продукты", "Кафе и рестораны", "Транспорт", "Жилье", 
            "Коммунальные услуги", "Связь и интернет", "Одежда", 
            "Развлечения", "Здоровье", "Образование", "Другое"
        ]
        
        print("\nКатегории:")
        for i, category in enumerate(categories, 1):
            print(f"{i}. {category}")
            
        cat_choice = input("Выберите категорию (или введите свою): ")
        
        try:
            category = categories[int(cat_choice) - 1]
        except (ValueError, IndexError):
            category = cat_choice
        
        success, message = self.tracker.add_planned_payment(account_id, amount, description, planned_date, category)
        self.print_message(message, success)

    def edit_planned_payment(self):
        self.print_header("РЕДАКТИРОВАНИЕ ЗАПЛАНИРОВАННОГО ПЛАТЕЖА")
        payments = self.tracker.get_planned_payments(True)  # Только активные, с виртуальными ID
        
        if not payments:
            self.print_message("У вас нет активных запланированных платежей", False)
            return
        
        print("Выберите платеж для редактирования:")
        for p in payments:
            payment_id, account_id, account_name, amount, description, category, planned_date, completed, real_id = p
            date = datetime.datetime.strptime(planned_date, "%Y-%m-%d").strftime("%d.%m.%y")
            category_str = f"[{category}]" if category else ""
            print(f"{payment_id}. {description} {category_str} - {amount} ₽ с '{account_name}' (дата: {date})")
        
        payment_id = int(self.input_number("Введите номер платежа: ", 1, len(payments)))
        
        # Находим выбранный платеж
        selected_payment = None
        for p in payments:
            if p[0] == payment_id:
                selected_payment = p
                break
        
        payment_id, old_account_id, old_account_name, old_amount, old_description, old_category, old_planned_date, _, real_id = selected_payment
        
        print(f"\nРедактирование платежа: {old_description}")
        
        # Запрашиваем новые значения или оставляем старые
        new_account_id = None
        change_account = input("Изменить счёт? (д/н): ")
        if change_account.lower() in ['д', 'y', 'да', 'yes']:
            new_account_id = self.select_account()
        
        new_description = input(f"Введите новое описание (или оставьте пустым для '{old_description}'): ")
        if not new_description:
            new_description = None
        
        new_amount_str = input(f"Введите новую сумму (или оставьте пустым для '{old_amount}'): ")
        new_amount = float(new_amount_str) if new_amount_str else None
        
        change_category = input("Изменить категорию? (д/н): ")
        if change_category.lower() in ['д', 'y', 'да', 'yes']:
            new_category = self.select_category("Выберите новую категорию:")
        else:
            new_category = None
        
        change_date = input("Изменить дату платежа? (д/н): ")
        if change_date.lower() in ['д', 'y', 'да', 'yes']:
            new_planned_date = self.input_date("Введите новую дату платежа")
        else:
            new_planned_date = None
        
        # Подтверждение
        print("\nНовые данные:")
        print(f"Счёт: {self.tracker.get_account_by_id(new_account_id)[1] if new_account_id else old_account_name}")
        print(f"Описание: {new_description if new_description is not None else old_description}")
        print(f"Сумма: {new_amount if new_amount is not None else old_amount} ₽")
        print(f"Категория: {new_category if new_category is not None else old_category}")
        print(f"Дата: {datetime.datetime.strptime(new_planned_date, '%Y-%m-%d').strftime('%d.%m.%Y') if new_planned_date else datetime.datetime.strptime(old_planned_date, '%Y-%m-%d').strftime('%d.%m.%Y')}")
        
        if not self.input_yes_no("\nСохранить изменения? (д/н): "):
            self.print_message("Редактирование отменено")
            return
        
        # Используем реальный ID вместо виртуального
        success, message = self.tracker.update_planned_payment(
            real_id,  # Используем реальный ID из БД 
            account_id=new_account_id,
            amount=new_amount,
            description=new_description,
            category=new_category,
            planned_date=new_planned_date
        )
        
        self.print_message(message, success)
    
    def execute_planned_payment(self):
        self.print_header("ВЫПОЛНЕНИЕ ЗАПЛАНИРОВАННОГО ПЛАТЕЖА")
        payments = self.tracker.get_planned_payments(True)  # Только активные
        
        if not payments:
            self.print_message("У вас нет активных запланированных платежей", False)
            return
        
        print("Выберите платеж для выполнения:")
        for p in payments:
            # Учитываем, что в p теперь 9 элементов, а не 8
            payment_id, account_id, account_name, amount, description, category, planned_date, completed, real_id = p
            date = datetime.datetime.strptime(planned_date, "%Y-%m-%d").strftime("%d.%m.%y")
            category_str = f"[{category}]" if category else ""
            print(f"{payment_id}. {description} {category_str} - {amount} ₽ с '{account_name}' (дата: {date})")
        
        payment_id = int(self.input_number("Введите ID платежа: ", 1))
        
        # Проверяем, что платеж существует и активен
        found = False
        for p in payments:
            if p[0] == payment_id:
                found = True
                break
        
        if not found:
            self.print_message("Платеж не найден или уже выполнен", False)
            return
        
        if not self.input_yes_no(f"Вы уверены, что хотите выполнить этот платеж сейчас? (д/н): "):
            self.print_message("Выполнение отменено")
            return
        
        success, message = self.tracker.execute_planned_payment(payment_id)
        self.print_message(message, success)
    
    def delete_planned_payment(self):
        self.print_header("УДАЛЕНИЕ ЗАПЛАНИРОВАННОГО ПЛАТЕЖА")
        payments = self.tracker.get_planned_payments(True)  # Только активные, с виртуальными ID
        
        if not payments:
            self.print_message("У вас нет активных запланированных платежей", False)
            return
        
        print("Выберите платеж для удаления:")
        for p in payments:
            payment_id, account_id, account_name, amount, description, category, planned_date, completed, real_id = p
            date = datetime.datetime.strptime(planned_date, "%Y-%m-%d").strftime("%d.%m.%y")
            print(f"{payment_id}. {description} - {amount} ₽ с '{account_name}' (дата: {date})")
        
        payment_id = int(self.input_number("Введите номер платежа: ", 1, len(payments)))
        
        # Находим выбранный платеж по виртуальному ID
        selected_payment = None
        for p in payments:
            if p[0] == payment_id:
                selected_payment = p
                break
        
        if not selected_payment:
            self.print_message("Платеж не найден", False)
            return
        
        # Получаем реальный ID из последнего элемента кортежа
        real_id = selected_payment[-1]
        
        if not self.input_yes_no(f"Вы уверены, что хотите удалить этот запланированный платеж? (д/н): "):
            self.print_message("Удаление отменено")
            return
        
        # Используем реальный ID
        success, message = self.tracker.delete_planned_payment(real_id)
        self.print_message(message, success)
    
    def reports_menu(self):
        while True:
            self.print_header("ОТЧЁТЫ И СТАТИСТИКА")
            print("1. 📊 Статистика по категориям расходов")
            print("2. 📅 Ежемесячный отчёт")
            print("3. 📈 Сравнительная статистика (день/неделя/месяц)")
            print("0. 🔙 Назад")
            
            choice = self.input_number("Выберите отчёт: ", 0, 3)
            
            if choice == 1:
                self.category_report()
            elif choice == 2:
                self.monthly_report()
            elif choice == 3:
                self.comparative_stats()
            elif choice == 0:
                break
    
    def category_report(self):
        self.print_header("РАСХОДЫ И ДОХОДЫ ПО КАТЕГОРИЯМ")
        
        print("Выберите тип отчета:")
        print("1. 💸 Только расходы")
        print("2. 💰 Только доходы")
        print("3. 🔄 Расходы и доходы")
        
        report_type_choice = self.input_number("Выберите вариант: ", 1, 3)
        
        transaction_type = None
        if report_type_choice == 1:
            transaction_type = "expense"
            report_title = "РАСХОДЫ ПО КАТЕГОРИЯМ"
        elif report_type_choice == 2:
            transaction_type = "income"
            report_title = "ДОХОДЫ ПО КАТЕГОРИЯМ"
        else:
            report_title = "РАСХОДЫ И ДОХОДЫ ПО КАТЕГОРИЯМ"
        
        print("\nВыберите период:")
        print("1. Текущий месяц")
        print("2. Предыдущий месяц")
        print("3. Текущий год")
        print("4. Произвольный период")
        
        choice = self.input_number("Выберите вариант: ", 1, 4)
        
        today = datetime.date.today()
        start_date = None
        end_date = None
        
        if choice == 1:  # Текущий месяц
            start_date = today.replace(day=1).strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")
        elif choice == 2:  # Предыдущий месяц
            last_month = today.month - 1
            year = today.year
            if last_month == 0:
                last_month = 12
                year -= 1
                
            start_date = datetime.date(year, last_month, 1).strftime("%Y-%m-%d")
            if last_month == 12:
                end_date = datetime.date(year, last_month, 31).strftime("%Y-%m-%d")
            else:
                end_date = (datetime.date(year, last_month + 1, 1) - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
                
        elif choice == 3:  # Текущий год
            start_date = today.replace(month=1, day=1).strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")
        elif choice == 4:  # Произвольный период
            start_date = self.input_date("Введите начальную дату")
            end_date = self.input_date("Введите конечную дату")
        
        summary = self.tracker.get_category_summary(start_date, end_date, transaction_type)
        
        if not summary:
            self.print_message("Нет данных за выбранный период", False)
            return
        
        self.print_header(report_title)
        
        # Группируем данные по типам транзакций
        expense_data = []
        income_data = []
        
        for category, trans_type, amount in summary:
            if trans_type == "expense":
                expense_data.append((category, amount))
            else:
                income_data.append((category, amount))
        
        # Вычисляем общие суммы
        total_expense = sum(abs(amount) for _, amount in expense_data)
        total_income = sum(amount for _, amount in income_data)
        
        # Выводим данные в зависимости от выбранного отчета
        if report_type_choice in [1, 3] and expense_data:
            print("\n💸 РАСХОДЫ:")
            print(f"{'Категория':<20} {'Сумма':<10} {'Доля':<10}")
            print("-" * 40)
            
            # Сортируем по убыванию суммы (по модулю)
            expense_data.sort(key=lambda x: abs(x[1]), reverse=True)
            
            for category, amount in expense_data:
                percent = abs(amount) / total_expense * 100 if total_expense else 0
                emoji = self.get_category_emoji(category)
                # Используем абсолютное значение для вывода, так как расходы хранятся как отрицательные числа
                print(f"{emoji} {category:<18} {abs(amount):<10.2f} {percent:<10.2f}%")
            
            print("-" * 40)
            print(f"💰 {'ИТОГО РАСХОДЫ':<18} {total_expense:<10.2f} {'100.00':<10}%")
        
        if report_type_choice in [2, 3] and income_data:
            if report_type_choice == 3:
                print("\n")  # Разделитель между расходами и доходами
                
            print("\n💰 ДОХОДЫ:")
            print(f"{'Категория':<20} {'Сумма':<10} {'Доля':<10}")
            print("-" * 40)
            
            # Сортируем по убыванию суммы
            income_data.sort(key=lambda x: x[1], reverse=True)
            
            for category, amount in income_data:
                percent = amount / total_income * 100 if total_income else 0
                emoji = self.get_category_emoji(category)
                print(f"{emoji} {category:<18} {amount:<10.2f} {percent:<10.2f}%")
            
            print("-" * 40)
            print(f"💰 {'ИТОГО ДОХОДЫ':<18} {total_income:<10.2f} {'100.00':<10}%")
        
        # Если отображаем оба типа, выводим соотношение
        if report_type_choice == 3 and total_income > 0:
            ratio = (total_expense / total_income) * 100
            print("\n" + "-" * 40)
            print(f"📊 Отношение расходы/доходы: {ratio:.2f}%")
            direction = "💸" if ratio > 100 else "💰"
            print(f"{direction} Вы {'тратите больше чем зарабатываете' if ratio > 100 else 'зарабатываете больше чем тратите'}")
        
        input("\n👉 Нажмите Enter, чтобы продолжить...")
        
    def get_category_emoji(self, category):
        emoji_map = {
            "Продукты": "🍎",
            "Кафе и рестораны": "🍽️",
            "Транспорт": "🚗",
            "Жилье": "🏠",
            "Коммунальные услуги": "💡",
            "Связь и интернет": "📱",
            "Одежда": "👕",
            "Развлечения": "🎮",
            "Здоровье": "⚕️",
            "Образование": "📚",
            "Подписки": "📺",
            "Кредит": "💳",
            "Аренда": "🏢",
            "Коммуналка": "💦",
            "Связь": "📞",
            "Страховка": "📝"
        }
        return emoji_map.get(category, "💸")
    
    def monthly_report(self):
        self.print_header("ЕЖЕМЕСЯЧНЫЙ ОТЧЁТ")
        
        year = datetime.datetime.now().year
        year_input = input(f"Введите год (или оставьте пустым для {year}): ")
        
        if year_input:
            try:
                year = int(year_input)
            except ValueError:
                self.print_message("Некорректный формат года", False)
                return
        
        monthly_data = self.tracker.get_monthly_summary(year)
        
        if not any(income != 0 or expense != 0 for _, income, expense, _ in monthly_data):
            self.print_message(f"Нет данных за {year} год", False)
            return
        
        self.print_header(f"ОТЧЁТ ЗА {year} ГОД")
        
        # Выводим таблицу
        print(f"{'Месяц':<12} {'Доходы':<12} {'Расходы':<12} {'Баланс':<12} {'Расход/Доход':<12}")
        print("-" * 65)
        
        total_income = 0
        total_expense = 0
        
        for month, income, expense, balance in monthly_data:
            # Пропускаем месяцы без операций
            if income == 0 and expense == 0:
                continue
                
            total_income += income
            total_expense += expense
            
            # Вычисляем соотношение расход/доход
            if income > 0:
                ratio = (abs(expense) / income) * 100
                ratio_str = f"{ratio:.1f}%"
            else:
                ratio_str = "∞"
            
            # Добавляем эмодзи в зависимости от баланса
            balance_emoji = "📈" if balance > 0 else "📉" if balance < 0 else "⚖️"
            print(f"{month:<12} {income:<12.2f} {abs(expense):<12.2f} {balance_emoji} {balance:<8.2f} {ratio_str:<12}")
        
        print("-" * 65)
        total_balance = total_income + total_expense  # expense уже отрицательный
        balance_emoji = "📈" if total_balance > 0 else "📉" if total_balance < 0 else "⚖️"
        
        # Вычисляем соотношение для итогов
        if total_income > 0:
            total_ratio = (abs(total_expense) / total_income) * 100
            total_ratio_str = f"{total_ratio:.1f}%"
        else:
            total_ratio_str = "∞"
        
        print(f"{'ИТОГО':<12} {total_income:<12.2f} {abs(total_expense):<12.2f} {balance_emoji} {total_balance:<8.2f} {total_ratio_str:<12}")
        
        # Добавляем интерпретацию соотношения для общего результата
        if total_income > 0:
            print("\n💡 ИТОГОВАЯ ОЦЕНКА:")
            if total_ratio < 50:
                print("🔥 Супер! Вы тратите меньше половины доходов - отлично копите!")
            elif total_ratio < 80:
                print("👍 Хорошо! Ваши расходы меньше доходов - у вас здоровый бюджет.")
            elif total_ratio < 100:
                print("⚠️ Внимание! Вы тратите почти все свои доходы.")
            else:
                print("🚨 Тревога! Ваши расходы превышают доходы - бюджет в минусе!")
        
        input("\n👉 Нажмите Enter, чтобы продолжить...")

    def comparative_stats(self):
        while True:
            self.print_header("СРАВНИТЕЛЬНАЯ СТАТИСТИКА")
            print("1. 📆 По дням (сегодня vs вчера)")
            print("2. 📆 По неделям (текущая vs предыдущая)")
            print("3. 📆 По месяцам (текущий vs предыдущий)")
            print("0. 🔙 Назад")
            
            choice = self.input_number("Выберите период: ", 0, 3)
            
            if choice == 1:
                self.show_day_comparison()
            elif choice == 2:
                self.show_week_comparison()
            elif choice == 3:
                self.show_month_comparison()
            elif choice == 0:
                break

    def show_day_comparison(self):
        self.print_header("СРАВНЕНИЕ ПО ДНЯМ")
        
        stats = self.tracker.get_day_comparison()
        
        print(f"💸 Расходы сегодня ({stats['today_date']}): {stats['today_expenses']:.2f} ₽")
        print(f"💸 Расходы вчера ({stats['yesterday_date']}): {stats['yesterday_expenses']:.2f} ₽")
        
        if stats['expense_percent_change'] > 0:
            print(f"📈 Сегодня вы потратили на {stats['expense_percent_change']:.2f}% БОЛЬШЕ, чем вчера")
        elif stats['expense_percent_change'] < 0:
            print(f"📉 Сегодня вы потратили на {abs(stats['expense_percent_change']):.2f}% МЕНЬШЕ, чем вчера")
        else:
            print("⚖️ Расходы не изменились")
        
        print("\n" + "-" * 40)
        
        print(f"💰 Доходы сегодня ({stats['today_date']}): {stats['today_income']:.2f} ₽")
        print(f"💰 Доходы вчера ({stats['yesterday_date']}): {stats['yesterday_income']:.2f} ₽")
        
        if stats['income_percent_change'] > 0:
            print(f"📈 Сегодня вы заработали на {stats['income_percent_change']:.2f}% БОЛЬШЕ, чем вчера")
        elif stats['income_percent_change'] < 0:
            print(f"📉 Сегодня вы заработали на {abs(stats['income_percent_change']):.2f}% МЕНЬШЕ, чем вчера")
        else:
            print("⚖️ Доходы не изменились")
        
        # Отображаем соотношение расход/доход
        print("\n" + "-" * 40 + "\n")
        print("📊 СООТНОШЕНИЕ РАСХОД/ДОХОД (в процентах):")
        
        if stats['today_ratio'] is not None:
            print(f"Сегодня: {stats['today_ratio']:.2f}%")
        else:
            print("Сегодня: Нет доходов")
            
        if stats['yesterday_ratio'] is not None:
            print(f"Вчера: {stats['yesterday_ratio']:.2f}%")
        else:
            print("Вчера: Нет доходов")
        
        if stats['today_ratio'] is not None and stats['yesterday_ratio'] is not None:
            if stats['ratio_percent_change'] > 0:
                print(f"📈 Сегодня соотношение увеличилось на {stats['ratio_percent_change']:.2f}%")
            elif stats['ratio_percent_change'] < 0:
                print(f"📉 Сегодня соотношение уменьшилось на {abs(stats['ratio_percent_change']):.2f}%")
            else:
                print("⚖️ Соотношение не изменилось")
        
        input("\n👉 Нажмите Enter, чтобы продолжить...")

    def show_week_comparison(self):
        self.print_header("СРАВНЕНИЕ ПО НЕДЕЛЯМ")
        
        stats = self.tracker.get_week_comparison()
        
        # Выводим информацию о расходах
        print(f"💸 РАСХОДЫ:")
        print(f"Текущая неделя ({stats['current_week_start']} - {stats['current_week_end']}): {stats['current_week_expenses']:.2f} ₽")
        print(f"Прошлая неделя ({stats['prev_week_start']} - {stats['prev_week_end']}): {stats['prev_week_expenses']:.2f} ₽")
        
        if stats['expense_percent_change'] > 0:
            print(f"📈 На этой неделе вы потратили на {stats['expense_percent_change']:.2f}% БОЛЬШЕ, чем на прошлой")
        elif stats['expense_percent_change'] < 0:
            print(f"📉 На этой неделе вы потратили на {abs(stats['expense_percent_change']):.2f}% МЕНЬШЕ, чем на прошлой")
        else:
            print("⚖️ Расходы не изменились")
        
        print("\n" + "-" * 40)
        
        # Выводим информацию о доходах
        print(f"💰 ДОХОДЫ:")
        print(f"Текущая неделя ({stats['current_week_start']} - {stats['current_week_end']}): {stats['current_week_income']:.2f} ₽")
        print(f"Прошлая неделя ({stats['prev_week_start']} - {stats['prev_week_end']}): {stats['prev_week_income']:.2f} ₽")
        
        if stats['income_percent_change'] > 0:
            print(f"📈 На этой неделе вы заработали на {stats['income_percent_change']:.2f}% БОЛЬШЕ, чем на прошлой")
        elif stats['income_percent_change'] < 0:
            print(f"📉 На этой неделе вы заработали на {abs(stats['income_percent_change']):.2f}% МЕНЬШЕ, чем на прошлой")
        else:
            print("⚖️ Доходы не изменились")
        
        # Отображаем соотношение расход/доход
        print("\n" + "-" * 40 + "\n")
        print("📊 СООТНОШЕНИЕ РАСХОД/ДОХОД (в процентах):")
        
        if stats['current_week_ratio'] is not None:
            print(f"Текущая неделя: {stats['current_week_ratio']:.2f}%")
        else:
            print("Текущая неделя: Нет доходов")
            
        if stats['prev_week_ratio'] is not None:
            print(f"Прошлая неделя: {stats['prev_week_ratio']:.2f}%")
        else:
            print("Прошлая неделя: Нет доходов")
        
        if stats['current_week_ratio'] is not None and stats['prev_week_ratio'] is not None:
            if stats['ratio_percent_change'] > 0:
                print(f"📈 На этой неделе соотношение увеличилось на {stats['ratio_percent_change']:.2f}%")
            elif stats['ratio_percent_change'] < 0:
                print(f"📉 На этой неделе соотношение уменьшилось на {abs(stats['ratio_percent_change']):.2f}%")
            else:
                print("⚖️ Соотношение не изменилось")
        
        # Интерпретация соотношения
        if stats['current_week_ratio'] is not None:
            print("\n💡 ИНТЕРПРЕТАЦИЯ:")
            if stats['current_week_ratio'] < 50:
                print("🔥 Супер! Вы тратите меньше половины доходов - отлично копите!")
            elif stats['current_week_ratio'] < 80:
                print("👍 Хорошо! Ваши расходы меньше доходов - у вас здоровый бюджет.")
            elif stats['current_week_ratio'] < 100:
                print("⚠️ Внимание! Вы тратите почти все свои доходы.")
            else:
                print("🚨 Тревога! Ваши расходы превышают доходы - бюджет в минусе!")
        
        input("\n👉 Нажмите Enter, чтобы продолжить...")

    def show_month_comparison(self):
        self.print_header("СРАВНЕНИЕ ПО МЕСЯЦАМ")
        
        stats = self.tracker.get_month_comparison()
        
        # Выводим информацию о расходах
        print(f"💸 РАСХОДЫ:")
        print(f"Текущий месяц ({stats['current_month']}): {stats['current_month_expenses']:.2f} ₽")
        print(f"Прошлый месяц ({stats['prev_month']}): {stats['prev_month_expenses']:.2f} ₽")
        
        if stats['expense_percent_change'] > 0:
            print(f"📈 В этом месяце вы потратили на {stats['expense_percent_change']:.2f}% БОЛЬШЕ, чем в прошлом")
        elif stats['expense_percent_change'] < 0:
            print(f"📉 В этом месяце вы потратили на {abs(stats['expense_percent_change']):.2f}% МЕНЬШЕ, чем в прошлом")
        else:
            print("⚖️ Расходы не изменились")
        
        print("\n" + "-" * 40)
        
        # Выводим информацию о доходах
        print(f"💰 ДОХОДЫ:")
        print(f"Текущий месяц ({stats['current_month']}): {stats['current_month_income']:.2f} ₽")
        print(f"Прошлый месяц ({stats['prev_month']}): {stats['prev_month_income']:.2f} ₽")
        
        if stats['income_percent_change'] > 0:
            print(f"📈 В этом месяце вы заработали на {stats['income_percent_change']:.2f}% БОЛЬШЕ, чем в прошлом")
        elif stats['income_percent_change'] < 0:
            print(f"📉 В этом месяце вы заработали на {abs(stats['income_percent_change']):.2f}% МЕНЬШЕ, чем в прошлом")
        else:
            print("⚖️ Доходы не изменились")
        
        # Отображаем соотношение расход/доход
        print("\n" + "-" * 40 + "\n")
        print("📊 СООТНОШЕНИЕ РАСХОД/ДОХОД (в процентах):")
        
        if stats['current_month_ratio'] is not None:
            print(f"Текущий месяц: {stats['current_month_ratio']:.2f}%")
        else:
            print("Текущий месяц: Нет доходов")
            
        if stats['prev_month_ratio'] is not None:
            print(f"Прошлый месяц: {stats['prev_month_ratio']:.2f}%")
        else:
            print("Прошлый месяц: Нет доходов")
        
        if stats['current_month_ratio'] is not None and stats['prev_month_ratio'] is not None:
            if stats['ratio_percent_change'] > 0:
                print(f"📈 В этом месяце соотношение увеличилось на {stats['ratio_percent_change']:.2f}%")
            elif stats['ratio_percent_change'] < 0:
                print(f"📉 В этом месяце соотношение уменьшилось на {abs(stats['ratio_percent_change']):.2f}%")
            else:
                print("⚖️ Соотношение не изменилось")
        
        # Интерпретация соотношения
        if stats['current_month_ratio'] is not None:
            print("\n💡 ИНТЕРПРЕТАЦИЯ:")
            if stats['current_month_ratio'] < 50:
                print("🔥 Супер! Вы тратите меньше половины доходов - отлично копите!")
            elif stats['current_month_ratio'] < 80:
                print("👍 Хорошо! Ваши расходы меньше доходов - у вас здоровый бюджет.")
            elif stats['current_month_ratio'] < 100:
                print("⚠️ Внимание! Вы тратите почти все свои доходы.")
            else:
                print("🚨 Тревога! Ваши расходы превышают доходы - бюджет в минусе!")
        
        input("\n👉 Нажмите Enter, чтобы продолжить...")

    def input_yes_no(self, prompt):
        """
        Запрашивает у пользователя ответ да/нет.
        Если пользователь нажал Enter без ввода, считаем это как "да".
        """
        response = input(prompt)
        # Пустая строка (просто Enter) считается как "да"
        if response == "":
            return True
        # В противном случае проверяем введённый ответ
        return response.lower() in ['д', 'y', 'да', 'yes']
    
    def display_welcome_emoji(self):
        """Отображает приветственное эмоджи-сообщение при запуске"""
        self.clear_screen()
        print("""
    💰💰💰💰💰💰💰💰💰💰💰💰💰💰💰
    💰                          💰
    💰   ФИНАНСОВЫЙ ТРЕКЕР 2.0  💰
    💰                          💰
    💰💰💰💰💰💰💰💰💰💰💰💰💰💰💰
        """)
        print("              💵 🤑 💵")
        print("             Контролируй")
        print("            свои финансы!")
        input("\n  👉 Нажмите Enter, чтобы начать...")

    def categories_menu(self):
        while True:
            self.print_header("УПРАВЛЕНИЕ КАТЕГОРИЯМИ")
            print("1. 💸 Категории расходов")
            print("2. 💰 Категории доходов")
            print("0. 🔙 Назад")
            
            choice = self.input_number("Выберите тип категорий: ", 0, 2)
            
            if choice == 1:
                self.expense_categories_menu()
            elif choice == 2:
                self.income_categories_menu()
            elif choice == 0:
                break

    def expense_categories_menu(self):
        while True:
            self.print_header("УПРАВЛЕНИЕ КАТЕГОРИЯМИ РАСХОДОВ")
            print("1. 👁️ Просмотр категорий")
            print("2. ➕ Добавить категорию")
            print("3. ✏️ Редактировать категорию")
            print("4. ❌ Удалить категорию")
            print("0. 🔙 Назад")
            
            choice = self.input_number("Выберите пункт меню: ", 0, 4)
            
            if choice == 1:
                self.show_expense_categories()
            elif choice == 2:
                self.add_expense_category()
            elif choice == 3:
                self.edit_expense_category()
            elif choice == 4:
                self.delete_expense_category()
            elif choice == 0:
                break

    def income_categories_menu(self):
        while True:
            self.print_header("УПРАВЛЕНИЕ КАТЕГОРИЯМИ ДОХОДОВ")
            print("1. 👁️ Просмотр категорий")
            print("2. ➕ Добавить категорию")
            print("3. ✏️ Редактировать категорию")
            print("4. ❌ Удалить категорию")
            print("0. 🔙 Назад")
            
            choice = self.input_number("Выберите пункт меню: ", 0, 4)
            
            if choice == 1:
                self.show_income_categories()
            elif choice == 2:
                self.add_income_category()
            elif choice == 3:
                self.edit_income_category()
            elif choice == 4:
                self.delete_income_category()
            elif choice == 0:
                break

    def show_expense_categories(self):
        self.print_header("СПИСОК КАТЕГОРИЙ РАСХОДОВ")
        categories = self.tracker.get_categories()
        
        if not categories:
            print("📭 У вас пока нет категорий расходов")
        else:
            for cat in categories:
                cat_id, name = cat
                print(f"{cat_id}. 💸 {name}")
        
        input("\n👉 Нажмите Enter, чтобы продолжить...")

    def add_expense_category(self):
        self.print_header("ДОБАВЛЕНИЕ КАТЕГОРИИ РАСХОДОВ")
        name = input("Введите название категории расходов: ")
        
        if not name:
            self.print_message("Название категории не может быть пустым", False)
            return
        
        success, message = self.tracker.add_category(name)
        self.print_message(message, success)

    def edit_expense_category(self):
        self.print_header("РЕДАКТИРОВАНИЕ КАТЕГОРИИ РАСХОДОВ")
        categories = self.tracker.get_categories()
        
        if not categories:
            self.print_message("У вас пока нет категорий расходов", False)
            return
        
        print("Выберите категорию для редактирования:")
        for cat in categories:
            cat_id, name = cat
            print(f"{cat_id}. 💸 {name}")
        
        category_id = int(self.input_number("Введите ID категории: ", 1))
        
        # Проверяем, существует ли категория
        selected_category = self.tracker.get_category_by_id(category_id)
        if not selected_category:
            self.print_message("Категория не найдена", False)
            return
        
        new_name = input(f"Введите новое название (текущее: {selected_category[1]}): ")
        
        if not new_name:
            self.print_message("Название категории не может быть пустым", False)
            return
        
        success, message = self.tracker.update_category(category_id, new_name)
        self.print_message(message, success)

    def delete_expense_category(self):
        self.print_header("УДАЛЕНИЕ КАТЕГОРИИ РАСХОДОВ")
        categories = self.tracker.get_categories()
        
        if not categories:
            self.print_message("У вас пока нет категорий расходов", False)
            return
        
        print("Выберите категорию для удаления:")
        for cat in categories:
            cat_id, name = cat
            print(f"{cat_id}. 💸 {name}")
        
        category_id = int(self.input_number("Введите ID категории: ", 1))
        
        # Проверяем, существует ли категория
        selected_category = self.tracker.get_category_by_id(category_id)
        if not selected_category:
            self.print_message("Категория не найдена", False)
            return
        
        if not self.input_yes_no(f"Вы уверены, что хотите удалить категорию '{selected_category[1]}'? (д/н): "):
            self.print_message("Удаление отменено")
            return
        
        success, message = self.tracker.delete_category(category_id)
        self.print_message(message, success)

    def show_income_categories(self):
        self.print_header("СПИСОК КАТЕГОРИЙ ДОХОДОВ")
        categories = self.tracker.get_income_categories()
        
        if not categories:
            print("📭 У вас пока нет категорий доходов")
        else:
            for cat in categories:
                cat_id, name = cat
                print(f"{cat_id}. 💰 {name}")
        
        input("\n👉 Нажмите Enter, чтобы продолжить...")

    def add_income_category(self):
        self.print_header("ДОБАВЛЕНИЕ КАТЕГОРИИ ДОХОДОВ")
        name = input("Введите название категории доходов: ")
        
        if not name:
            self.print_message("Название категории не может быть пустым", False)
            return
        
        success, message = self.tracker.add_income_category(name)
        self.print_message(message, success)

    def edit_income_category(self):
        self.print_header("РЕДАКТИРОВАНИЕ КАТЕГОРИИ ДОХОДОВ")
        categories = self.tracker.get_income_categories()
        
        if not categories:
            self.print_message("У вас пока нет категорий доходов", False)
            return
        
        print("Выберите категорию для редактирования:")
        for cat in categories:
            cat_id, name = cat
            print(f"{cat_id}. 💰 {name}")
        
        category_id = int(self.input_number("Введите ID категории: ", 1))
        
        # Проверяем, существует ли категория
        selected_category = self.tracker.get_income_category_by_id(category_id)
        if not selected_category:
            self.print_message("Категория не найдена", False)
            return
        
        new_name = input(f"Введите новое название (текущее: {selected_category[1]}): ")
        
        if not new_name:
            self.print_message("Название категории не может быть пустым", False)
            return
        
        success, message = self.tracker.update_income_category(category_id, new_name)
        self.print_message(message, success)

    def delete_income_category(self):
        self.print_header("УДАЛЕНИЕ КАТЕГОРИИ ДОХОДОВ")
        categories = self.tracker.get_income_categories()
        
        if not categories:
            self.print_message("У вас пока нет категорий доходов", False)
            return
        
        print("Выберите категорию для удаления:")
        for cat in categories:
            cat_id, name = cat
            print(f"{cat_id}. 💰 {name}")
        
        category_id = int(self.input_number("Введите ID категории: ", 1))
        
        # Проверяем, существует ли категория
        selected_category = self.tracker.get_income_category_by_id(category_id)
        if not selected_category:
            self.print_message("Категория не найдена", False)
            return
        
        if not self.input_yes_no(f"Вы уверены, что хотите удалить категорию '{selected_category[1]}'? (д/н): "):
            self.print_message("Удаление отменено")
            return
        
        success, message = self.tracker.delete_income_category(category_id)
        self.print_message(message, success)

    def show_categories(self):
        self.print_header("СПИСОК КАТЕГОРИЙ")
        categories = self.tracker.get_categories()
        
        if not categories:
            print("📭 У вас пока нет категорий")
        else:
            for cat in categories:
                cat_id, name = cat
                print(f"{cat_id}. {name}")
        
        input("\n👉 Нажмите Enter, чтобы продолжить...")

    def add_category(self):
        self.print_header("ДОБАВЛЕНИЕ КАТЕГОРИИ")
        name = input("Введите название категории: ")
        
        if not name:
            self.print_message("Название категории не может быть пустым", False)
            return
        
        success, message = self.tracker.add_category(name)
        self.print_message(message, success)

    def edit_category(self):
        self.print_header("РЕДАКТИРОВАНИЕ КАТЕГОРИИ")
        categories = self.tracker.get_categories()
        
        if not categories:
            self.print_message("У вас пока нет категорий", False)
            return
        
        print("Выберите категорию для редактирования:")
        for cat in categories:
            cat_id, name = cat
            print(f"{cat_id}. {name}")
        
        category_id = int(self.input_number("Введите ID категории: ", 1))
        
        # Проверяем, существует ли категория
        selected_category = self.tracker.get_category_by_id(category_id)
        if not selected_category:
            self.print_message("Категория не найдена", False)
            return
        
        new_name = input(f"Введите новое название (текущее: {selected_category[1]}): ")
        
        if not new_name:
            self.print_message("Название категории не может быть пустым", False)
            return
        
        success, message = self.tracker.update_category(category_id, new_name)
        self.print_message(message, success)

    def delete_category(self):
        self.print_header("УДАЛЕНИЕ КАТЕГОРИИ")
        categories = self.tracker.get_categories()
        
        if not categories:
            self.print_message("У вас пока нет категорий", False)
            return
        
        print("Выберите категорию для удаления:")
        for cat in categories:
            cat_id, name = cat
            print(f"{cat_id}. {name}")
        
        category_id = int(self.input_number("Введите ID категории: ", 1))
        
        # Проверяем, существует ли категория
        selected_category = self.tracker.get_category_by_id(category_id)
        if not selected_category:
            self.print_message("Категория не найдена", False)
            return
        
        if not self.input_yes_no(f"Вы уверены, что хотите удалить категорию '{selected_category[1]}'? (д/н): "):
            self.print_message("Удаление отменено")
            return
        
        success, message = self.tracker.delete_category(category_id)
        self.print_message(message, success)

    def select_expense_category(self, prompt="Выберите категорию расхода:"):
        categories = self.tracker.get_categories()  # Это для расходов
        if not categories:
            print("Нет доступных категорий расходов")
            return None
        
        print(prompt)
        for i, category in enumerate(categories, 1):
            print(f"{i}. {category[1]}")
        print("0. Ввести новую категорию")
        
        choice = self.input_number("Введите номер категории: ", 0, len(categories))
        
        if choice == 0:
            new_category = input("Введите название новой категории расхода: ")
            if new_category:
                success, _ = self.tracker.add_category(new_category)
                if success:
                    category = self.tracker.get_category_by_name(new_category)
                    return category[1] if category else new_category
                return new_category
            return ""
        
        return categories[int(choice) - 1][1]  # Возвращаем название выбранной категории

    def select_income_category(self, prompt="Выберите категорию дохода:"):
        categories = self.tracker.get_income_categories()  # Для доходов
        if not categories:
            print("Нет доступных категорий доходов")
            return None
        
        print(prompt)
        for i, category in enumerate(categories, 1):
            print(f"{i}. {category[1]}")
        print("0. Ввести новую категорию")
        
        choice = self.input_number("Введите номер категории: ", 0, len(categories))
        
        if choice == 0:
            new_category = input("Введите название новой категории дохода: ")
            if new_category:
                success, _ = self.tracker.add_income_category(new_category)
                if success:
                    category = self.tracker.get_income_category_by_name(new_category)
                    return category[1] if category else new_category
                return new_category
            return ""
        
        return categories[int(choice) - 1][1]  # Возвращаем название выбранной категории

# Функция для запуска приложения
def main():
    ui = ConsoleUI()
    ui.display_welcome_emoji()
    ui.main_menu()


if __name__ == "__main__":
    main()
