import sqlite3
import requests
import diskcache
import telebot
import threading
import time

from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from telebot.types import ReplyKeyboardMarkup, KeyboardButton
from html import escape
from config import API_TOKEN
import collections
from time import gmtime, strftime
DB_PATH = "watch.db"

# ---------- SQLQ ----------
class SQLQ:
    """
    Class holding all SQL queries as class variables.
    """
    CREATE_TABLE = """
        CREATE TABLE IF NOT EXISTS user_watch (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            skin_market_hash_name TEXT NOT NULL,
            skin_item_page TEXT NOT NULL,
            target_price REAL NOT NULL,
            condition TEXT NOT NULL
        )
    """
    INSERT_WATCH = """
        INSERT INTO user_watch (chat_id, skin_market_hash_name, skin_item_page, target_price, condition)
        VALUES (?, ?, ?, ?, ?)
    """
    DELETE_WATCH = "DELETE FROM user_watch WHERE id = ?"
    UPDATE_WATCH = "UPDATE user_watch SET target_price = ?, condition = ? WHERE id = ?"
    SELECT_USER_WATCHES = "SELECT * FROM user_watch WHERE chat_id = ?"
    SELECT_WATCH = "SELECT * FROM user_watch WHERE id = ? AND chat_id = ?"

    CREATE_REMINDER_TABLE = """
        CREATE TABLE IF NOT EXISTS user_reminder (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            skin_market_hash_name TEXT NOT NULL,
            skin_item_page TEXT NOT NULL,
            interval_minutes INTEGER NOT NULL
        )
    """
    INSERT_REMINDER = """
        INSERT INTO user_reminder (chat_id, skin_market_hash_name, skin_item_page, interval_minutes)
        VALUES (?, ?, ?, ?)
    """
    DELETE_REMINDER = "DELETE FROM user_reminder WHERE id = ?"
    SELECT_USER_REMINDERS = "SELECT * FROM user_reminder WHERE chat_id = ?"
    SELECT_ALL_REMINDERS = "SELECT * FROM user_reminder"
    UPDATE_REMINDER = "UPDATE user_reminder SET interval_minutes = ? WHERE id = ?"
# ---------- Dbase ----------
class Dbase:
    """
    Base class for database connection and table creation.
    """
    def __init__(self, db_path):
        """
        Initialize database connection and create table if not exists.

        Args:
            db_path (str): Path to SQLite database file.
        """
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.cur = self.conn.cursor()
        self.create_table()

    def create_table(self):
        """
        Create the user_watch table if it does not exist.
        """
        self.cur.execute(SQLQ.CREATE_TABLE)
        self.cur.execute(SQLQ.CREATE_REMINDER_TABLE)
        self.conn.commit()

    def close(self):
        """
        Close the database connection.
        """
        self.conn.close()



# ---------- Insert, Update, Select, Delete ----------
class UpdateReminder(Dbase):
    def update_reminder(self, reminder_id, new_interval):
        self.cur.execute(SQLQ.UPDATE_REMINDER, (new_interval, reminder_id))
        self.conn.commit()

class Insert(Dbase):
    """
    Class for inserting data into the database.
    """
    def add_watch(self, chat_id, skin_market_hash_name, skin_item_page, target_price, condition):
        """
        Insert a new watch record into the database.

        Args:
            chat_id (int): Telegram chat ID.
            skin_market_hash_name (str): Skin name.
            skin_item_page (str): Skin page URL.
            target_price (float): Target price.
            condition (str): '<' or '>'.

        Returns:
            int: The ID of the inserted watch.
        """
        self.cur.execute(SQLQ.INSERT_WATCH, (chat_id, skin_market_hash_name, skin_item_page, target_price, condition))
        self.conn.commit()
        return self.cur.lastrowid

class Update(Dbase):
    """
    Class for updating data in the database.
    """
    def update_watch(self, watch_id, target_price, condition):
        """
        Update the target price and condition for a watch.

        Args:
            watch_id (int): Watch ID.
            target_price (float): New target price.
            condition (str): '<' or '>'.
        """
        self.cur.execute(SQLQ.UPDATE_WATCH, (target_price, condition, watch_id))
        self.conn.commit()

class Select(Dbase):
    """
    Class for selecting data from the database.
    """
    def get_user_watches(self, chat_id):
        """
        Get all watches for a user.

        Args:
            chat_id (int): Telegram chat ID.

        Returns:
            list: List of watch dicts.
        """
        self.cur.execute(SQLQ.SELECT_USER_WATCHES, (chat_id,))
        columns = ["id", "chat_id", "skin_market_hash_name", "skin_item_page", "target_price", "condition"]
        return [dict(zip(columns, row)) for row in self.cur.fetchall()]

    def get_watch(self, watch_id, chat_id):
        """
        Get a specific watch by ID and user.

        Args:
            watch_id (int): Watch ID.
            chat_id (int): Telegram chat ID.

        Returns:
            dict or None: Watch dict or None if not found.
        """
        self.cur.execute(SQLQ.SELECT_WATCH, (watch_id, chat_id))
        row = self.cur.fetchone()
        if not row:
            return None
        columns = ["id", "chat_id", "skin_market_hash_name", "skin_item_page", "target_price", "condition"]
        return dict(zip(columns, row))

class Delete(Dbase):
    """
    Class for deleting data from the database.
    """
    def delete_watch(self, watch_id):
        """
        Delete a watch by ID.

        Args:
            watch_id (int): Watch ID.
        """
        self.cur.execute(SQLQ.DELETE_WATCH, (watch_id,))
        self.conn.commit()

class InsertReminder(Dbase):
    def add_reminder(self, chat_id, skin_market_hash_name, skin_item_page, interval_minutes):
        self.cur.execute(SQLQ.INSERT_REMINDER, (chat_id, skin_market_hash_name, skin_item_page, interval_minutes))
        self.conn.commit()
        return self.cur.lastrowid

class SelectReminder(Dbase):
    def get_user_reminders(self, chat_id):
        self.cur.execute(SQLQ.SELECT_USER_REMINDERS, (chat_id,))
        columns = ["id", "chat_id", "skin_market_hash_name", "skin_item_page", "interval_minutes"]
        return [dict(zip(columns, row)) for row in self.cur.fetchall()]

    def get_all_reminders(self):
        self.cur.execute(SQLQ.SELECT_ALL_REMINDERS)
        columns = ["id", "chat_id", "skin_market_hash_name", "skin_item_page", "interval_minutes"]
        return [dict(zip(columns, row)) for row in self.cur.fetchall()]

class DeleteReminder(Dbase):
    def delete_reminder(self, reminder_id):
        self.cur.execute(SQLQ.DELETE_REMINDER, (reminder_id,))
        self.conn.commit()
# ---------- Skins ----------
class Skins:
    """
    Class for loading and searching skins from the Skinport API or cache.
    """
    def __init__(self):
        """
        Initialize the Skins class and load skins from cache or API.
        """
        self.cache = diskcache.Cache("skinport_cache")
        self.cache_history = diskcache.Cache("skins_history_data")
        self.api_calls = collections.deque(maxlen=8)  # <-- Přesuň SEM!
        self.skins = self.load_skins()
        self.skins_history_data = self.skins_history()

    def start_auto_refresh(self, interval=120):
        def refresh_loop():
            while True:
                try:
                    self.skins = self.load_skins()
                    self.skins_history_data = self.skins_history()
                except Exception as e:
                    print(f"Error updating skins: {e}")

                time.sleep(interval)

        threading.Thread(target=refresh_loop, daemon=True).start()

    def load_skins(self):
        cached_skins = self.cache.get("skins_data")
        if cached_skins:
            print("✅ Loaded skins from cache.")
            return cached_skins
        self._wait_for_rate_limit()
        print("🔄 Downloading skins from Skinport API...")
        params = {"app_id": 730, "currency": "EUR"}
        url = "https://api.skinport.com/v1/items"
        response = requests.get(url, params=params, headers={"Accept-Encoding": "br", "Accept": "application/json"})
        skins = response.json()
        self.cache.set("skins_data", skins, expire=300)
        self.api_calls.append(time.time())
        print(f"Downloaded {len(skins)} skins.")
        return skins

    def skins_history(self):
        cached_skins = self.cache_history.get("skins_history_data")
        if cached_skins:
            print("✅ Loaded skins from cache.")
            return cached_skins
        self._wait_for_rate_limit()
        print("🔄 Downloading skins from Skinport API...")
        params = {"app_id": 730, "currency": "EUR"}
        url = "https://api.skinport.com/v1/sales/history"
        response = requests.get(url, params=params, headers={"Accept-Encoding": "br", "Accept": "application/json"})
        skins = response.json()
        self.cache_history.set("skins_history_data", skins, expire=300)
        self.api_calls.append(time.time())
        print(f"Downloaded {len(skins)} history skins.")
        return skins


    def find(self, query):
        """
        Find skins by name substring.

        Args:
            query (str): Substring to search for in skin names.

        Returns:
            list: List of matching skin dicts.
        """
        return [s for s in self.skins if query.lower() in s["market_hash_name"].lower()]

    def _wait_for_rate_limit(self):
        now = time.time()
        if len(self.api_calls) < 8:
            return
        # Pokud už bylo 8 dotazů, čekej, dokud nejstarší není starší než 5 minut
        oldest = self.api_calls[0]
        wait_time = 300 - (now - oldest)
        if wait_time > 0:
            print(f"Rate limit reached, waiting {wait_time:.1f} seconds...")
            time.sleep(wait_time)

# ---------- WatchBot ----------
class WatchBot:
    """
    Main class for the Telegram bot logic and handlers.
    """
    def __init__(self, api_token, db_path, skins):
        """
        Initialize the bot, register handlers, and prepare DB access.

        Args:
            api_token (str): Telegram bot token.
            db_path (str): Path to SQLite database.
            skins (Skins): Instance of Skins class.
        """
        self.bot = telebot.TeleBot(token=api_token)


        self.started_users = set()
        self.skins = skins
        self.db_insert = Insert(db_path)
        self.db_update = Update(db_path)
        self.db_select = Select(db_path)
        self.db_delete = Delete(db_path)
        self.db_insert_reminder = InsertReminder(db_path)
        self.db_select_reminder = SelectReminder(db_path)
        self.db_delete_reminder = DeleteReminder(db_path)
        self.db_update_reminder = UpdateReminder(db_path)
        self.running_reminders = {}
        self.user_remindskin_matches = {}
        self.user_skin_history_matches = {}

        self.user_watch_data = {}
        self.start_reminders()

        # Register handlers
        self.bot.message_handler(commands=["start"])(self.welcome)
        self.bot.message_handler(commands=["help"])(self.require_start(self.help))
        self.bot.message_handler(commands=["mywatch"])(self.require_start(self.list_user_watches))
        self.bot.message_handler(commands=["watchskin"])(self.require_start(self.ask_skin_name))
        self.bot.message_handler(commands=["findskin"])(self.require_start(self.find_func))
        self.bot.message_handler(commands=["historyskin"])(self.require_start(self.ask_skin_history))
        self.bot.message_handler(commands=["remindskin"])(self.require_start(self.remindskin_start))
        self.bot.message_handler(commands=["myreminders"])(self.require_start(self.list_user_reminders))

        #self.bot.message_handler(commands=["saleshistory"])(self.require_start(self.sales_history))
        self.bot.callback_query_handler(func=lambda call: call.data.startswith("select_skin_"))(self.callback_select_skin)
        self.bot.callback_query_handler(func=lambda call: call.data.startswith("select_watch_skin_"))(self.callback_watch_selected)
        self.bot.callback_query_handler(func=lambda call: call.data.startswith("delete_watch_"))(self.callback_delete_watch)
        self.bot.callback_query_handler(func=lambda call: call.data.startswith("change_watch_"))(self.callback_change_watch)
        self.bot.callback_query_handler(func=lambda call: call.data.startswith("history_skin_"))(self.callback_history_skin)
        self.bot.callback_query_handler(func=lambda call: call.data.startswith("remindskin_select_"))(self.remindskin_inline_selected)
        self.bot.callback_query_handler(func=lambda call: call.data.startswith("select_reminder_"))(self.callback_reminder_selected)
        self.bot.callback_query_handler(func=lambda call: call.data.startswith("delete_reminder_"))(self.callback_delete_reminder)
        self.bot.callback_query_handler(func=lambda call: call.data.startswith("change_reminder_"))(self.callback_change_reminder)

    def require_start(self, func):
        """
        Decorator to ensure user has used /start before other commands.

        Args:
            func (callable): Handler function to wrap.

        Returns:
            callable: Wrapped function.
        """
        def wrapper(message, *args, **kwargs):
            if message.chat.id not in self.started_users:
                self.bot.send_message(message.chat.id, "Please use /start before using other commands.")
                return
            return func(message, *args, **kwargs)
        return wrapper

    def help(self, message):
        self.bot.send_message(message.chat.id, f"Commands: \n /help - See all commands\n /start - Start a bot\n /findskin - Find s skin by a name\n /watchskin - Set target price on your skin and get notification\n /mywatch - See your watch list of skins, edit or delete\n /remindskin - Set a reminder for a selected skin\n /myreminders - See your reminders\n /historyskin - See sales and price history for selected skin\n\n Type exit if you want to cancel process")

    def welcome(self, message):
        """
        Handler for /start command. Registers user as started.

        Args:
            message (telebot.types.Message): Telegram message object.
        """
        self.started_users.add(message.chat.id)
        self.start_watch_user_data(message.chat.id)
        self.bot.send_message(message.chat.id, f"Welcome {message.from_user.first_name}! Use /watchskin to start watching a skin.")

    def check_exit(self, message):
        if message.text.strip().lower() == "exit":
            self.bot.send_message(message.chat.id, "Process cancelled.")
            return True
        return False

    def exit_guard(func):
        def wrapper(self, message, *args, **kwargs):
            if self.check_exit(message):
                return
            return func(self, message, *args, **kwargs)

        return wrapper


    def start_watch_user_data(self, chat_id):
        """
        Start watch threads for all user's watches.

        Args:
            chat_id (int): Telegram chat ID.
        """
        watch_list = self.db_select.get_user_watches(chat_id)
        for watch in watch_list:
            skin = self.skins.find(watch["skin_market_hash_name"])
            if skin:
                threading.Thread(
                    target=self.watch_price_loop,
                    args=(chat_id, skin[0], watch["target_price"], watch["condition"], watch["id"]),
                    daemon=True
                ).start()

    def watch_price_loop(self, chat_id, skin, target_price, condition, watch_id):
        """
        Thread function that checks the price of a skin and notifies the user if the target price is met.

        Args:
            chat_id (int): Telegram chat ID.
            skin (dict): Skin data.
            target_price (float): Target price.
            condition (str): '<' or '>'.
            watch_id (int): Watch ID in DB.
        """
        while True:
            try:
                current_price = skin['min_price']
                name = skin['market_hash_name']
                url = skin['item_page']
                if condition == '<' and current_price <= target_price:
                    self.bot.send_message(chat_id, f"✅ {name} is now {current_price} EUR (below {target_price} EUR)")
                    self.db_delete.delete_watch(watch_id)
                    return
                elif condition == '>' and current_price >= target_price:
                    self.bot.send_message(chat_id, f"✅ {name} is now {current_price} EUR (above {target_price} EUR)")
                    self.db_delete.delete_watch(watch_id)
                    return
                time.sleep(60)
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(60)

    def list_user_watches(self, message):
        """
        Handler for /mywatch command. Shows user's watches with inline buttons.

        Args:
            message (telebot.types.Message): Telegram message object.
        """
        watches = self.db_select.get_user_watches(message.chat.id)
        if not watches:
            self.bot.send_message(message.chat.id, "You are not watching any skins.")
        else:
            keyboard = InlineKeyboardMarkup(row_width=1)
            for watch in watches:
                label = f"{watch['skin_market_hash_name']} ({watch['condition']}{watch['target_price']} EUR)"
                callback_data = f"select_watch_skin_{watch['id']}"
                keyboard.add(InlineKeyboardButton(text=label, callback_data=callback_data))
            self.bot.send_message(message.chat.id, "Your watches:", reply_markup=keyboard)

    @exit_guard
    def find_func(self, message):
        """
        Handler for /findskin command. Asks user for skin name.

        Args:
            message (telebot.types.Message): Telegram message object.
        """
        self.bot.send_message(message.chat.id, "What skin are you looking for?")
        self.bot.register_next_step_handler(message, self.find_skin_reply)

    @exit_guard
    def find_skin_reply(self, message):
        """
        Processes user's skin search query and displays results.

        Args:
            message (telebot.types.Message): Telegram message object.
        """


        matches = self.skins.find(message.text)
        if not matches:
            self.bot.send_message(message.chat.id, "No skins found. Please try again or type 'exit' to cancel.")
            self.bot.register_next_step_handler(message, self.find_skin_reply)
            return

        skins_text = ""
        for skin in matches:
            name = escape(skin["market_hash_name"])
            url = skin["item_page"]
            min_price = skin.get('min_price')
            price = f"{min_price:.2f}" if min_price is not None else "N/A"
            skins_text += f'<a href="{url}">{name}</a> - {price} EUR\n'

        try:
            self.bot.send_message(message.chat.id, f"Skins found:\n{skins_text}", parse_mode="HTML")
        except Exception:
            self.bot.send_message(message.chat.id, "Too many results, please be more specific.")
            self.bot.register_next_step_handler(message, self.find_skin_reply)

    @exit_guard
    def ask_skin_name(self, message):
        """
        Handler for /watchskin command. Asks user for skin name to watch.

        Args:
            message (telebot.types.Message): Telegram message object.
        """
        self.bot.send_message(message.chat.id, "Enter the name of the skin you want to watch:")
        self.bot.register_next_step_handler(message, self.ask_price_target)

    @exit_guard
    def ask_price_target(self, message):
        """
        After user enters skin name, finds matches and continues.

        Args:
            message (telebot.types.Message): Telegram message object.
        """
        skin_name = message.text.strip().lower()


        matches = self.skins.find(message.text)
        if not matches:
            self.bot.send_message(message.chat.id, "Skin not found, please try again or type 'exit' to cancel.")
            self.bot.register_next_step_handler(message, self.ask_price_target)
            return

        if len(matches) == 1:
            self.user_watch_data[message.chat.id] = {"skin": matches[0]}
            self.bot.send_message(
                message.chat.id,
                f"{matches[0]['market_hash_name']} is currently {matches[0]['min_price']} EUR. "
                "Enter the target price (e.g. <10 or >20):"
            )
            self.bot.register_next_step_handler(message, self.start_watching)
        else:
            self.user_watch_data[message.chat.id] = {"matches": matches}
            keyboard = self.create_skins_keyboard(matches)
            self.bot.send_message(
                message.chat.id,
                "Multiple skins found, please select one:",
                reply_markup=keyboard
            )

    def create_skins_keyboard(self, matches):
        """
        Create an inline keyboard for selecting skins.

        Args:
            matches (list): List of skin dicts.

        Returns:
            InlineKeyboardMarkup: Keyboard with skin options.
        """
        keyboard = InlineKeyboardMarkup(row_width=1)
        for idx, skin in enumerate(matches):
            keyboard.add(InlineKeyboardButton(text=skin['market_hash_name'], callback_data=f"select_skin_{idx}"))
        return keyboard


    def callback_select_skin(self, call):
        """
        Callback handler for selecting a skin from the search results.

        Args:
            call (telebot.types.CallbackQuery): Callback query object.
        """
        chat_id = call.message.chat.id
        index = int(call.data.split("_")[-1])
        matches = self.user_watch_data.get(chat_id, {}).get("matches")
        if not matches or index >= len(matches):
            self.bot.answer_callback_query(call.id, "Invalid selection, please try again.")
            return
        selected_skin = matches[index]
        self.user_watch_data[chat_id] = {"skin": selected_skin}
        self.bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id,
                                   text=f"You selected: {selected_skin['market_hash_name']} (current price: {selected_skin['min_price']} EUR)")
        self.bot.send_message(chat_id, "Enter the target price (e.g. <10 or >20):")
        self.bot.register_next_step_handler_by_chat_id(chat_id, self.start_watching)

    @exit_guard
    def start_watching(self, message):
        """
        After user enters target price, starts watching the skin.

        Args:
            message (telebot.types.Message): Telegram message object.
        """
        chat_id = message.chat.id
        text = message.text.strip().replace(" ", "").lower()


        if text.startswith("<") or text.startswith(">"):
            try:
                condition = text[0]
                price = float(text[1:].replace(",", "."))
            except ValueError:
                self.bot.send_message(chat_id,
                                      "Invalid price format. Please enter a number, e.g. <10 or >20, or type 'exit' to cancel.")
                self.bot.register_next_step_handler(message, self.start_watching)
                return

            skin = self.user_watch_data.get(chat_id, {}).get("skin")
            if not skin:
                self.bot.send_message(chat_id, "Session expired, please start again.")
                return

            watch_id = self.db_insert.add_watch(chat_id, skin["market_hash_name"], skin["item_page"], price, condition)
            thread = threading.Thread(
                target=self.watch_price_loop,
                args=(chat_id, skin, price, condition, watch_id),
                daemon=True
            )
            thread.start()
            self.bot.send_message(
                chat_id,
                f"Started watching '{skin['market_hash_name']}' for target price: {condition}{price} EUR"
            )
        else:
            self.bot.send_message(chat_id,
                                  "Invalid format. Message must start with < or >, e.g. <10 or >20, or type 'exit' to cancel.")
            self.bot.register_next_step_handler(message, self.start_watching)

    def callback_watch_selected(self, call):
        """
        Callback handler for selecting a watch from the user's watch list.

        Args:
            call (telebot.types.CallbackQuery): Callback query object.
        """
        chat_id = call.message.chat.id
        watch_id = int(call.data.split("_")[-1])
        watch = self.db_select.get_watch(watch_id, chat_id)
        if not watch:
            self.bot.answer_callback_query(call.id, "Watch not found or does not belong to you.")
            return
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton(text="🗑️ Delete", callback_data=f"delete_watch_{watch['id']}"))
        keyboard.add(InlineKeyboardButton(text="✏️ Change", callback_data=f"change_watch_{watch['id']}"))
        msg = (f"🔍 <a href=\"{watch['skin_item_page']}\">{escape(watch['skin_market_hash_name'])}</a>\n"
               f"🎯 Target price: {escape(watch['condition'])}{watch['target_price']} EUR")
        self.bot.edit_message_text(chat_id=chat_id,
                                   message_id=call.message.message_id,
                                   text=msg,
                                   parse_mode="HTML",
                                   reply_markup=keyboard)

    def callback_delete_watch(self, call):
        """
        Callback handler for deleting a watch.

        Args:
            call (telebot.types.CallbackQuery): Callback query object.
        """
        watch_id = int(call.data.split("_")[-1])
        self.db_delete.delete_watch(watch_id)
        self.bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🗑️ Watch has been deleted.")


    def callback_change_watch(self, call):
        """
        Callback handler for changing the target price of a watch.

        Args:
            call (telebot.types.CallbackQuery): Callback query object.
        """
        chat_id = call.message.chat.id
        watch_id = int(call.data.split("_")[-1])

        self.user_watch_data[chat_id] = {"edit_watch_id": watch_id}
        self.bot.edit_message_text(chat_id = chat_id,message_id = call.message.id, text = "✏️ Enter a new target price (e.g. `<10` or `>20`):")
        self.bot.register_next_step_handler_by_chat_id(chat_id, self.handle_price_change)

    @exit_guard
    def handle_price_change(self, message):
        """
        Handles the user's input for changing the target price of a watch and restarts the watch thread.

        Args:
            message (telebot.types.Message): Telegram message object.
        """
        chat_id = message.chat.id
        text = message.text.strip().replace(" ", "")

        if text.startswith("<") or text.startswith(">"):
            try:
                condition = text[0]
                target_price = float(text[1:].replace(",", "."))
            except ValueError:
                self.bot.send_message(chat_id, "❌ Invalid price. Try again:")
                self.bot.register_next_step_handler(message, self.handle_price_change)
                return
        else:
            self.bot.send_message(chat_id, "❌ Format must be e.g. `<10` or `>20`.")
            self.bot.register_next_step_handler(message, self.handle_price_change)
            return
        watch_id = self.user_watch_data.get(chat_id, {}).get("edit_watch_id")
        if not watch_id:
            self.bot.send_message(chat_id, "⚠️ Session expired, please try again.")
            return
        self.db_update.update_watch(watch_id, target_price, condition)
        watch = self.db_select.get_watch(watch_id, chat_id)
        if not watch:
            self.bot.send_message(chat_id, "⚠️ Watch not found after update.")
            return
        skins_found = self.skins.find(watch["skin_market_hash_name"])
        if not skins_found:
            self.bot.send_message(chat_id, "⚠️ Skin data not found, cannot start watching.")
            return
        skin = skins_found[0]
        thread = threading.Thread(
            target=self.watch_price_loop,
            args=(chat_id, skin, target_price, condition, watch_id),
            daemon=True
        )
        thread.start()
        self.bot.send_message(chat_id, f"✅ Target price updated to: {condition}{target_price} EUR")
        del self.user_watch_data[chat_id]

    @exit_guard
    def ask_skin_history(self, message):
        self.bot.send_message(message.chat.id, "Enter the skin name to view history:")

        self.bot.register_next_step_handler(message, self.ask_skin_history_reply)

    @exit_guard
    def ask_skin_history_reply(self, message):
        matches = self.skins.find(message.text)

        if not matches:
            self.bot.send_message(message.chat.id, "Skin not found, please try again.")
            self.bot.register_next_step_handler(message, self.ask_skin_history_reply)
            return

        # Uložení výsledků podle chat ID
        self.user_skin_history_matches[message.chat.id] = matches

        keyboard = InlineKeyboardMarkup(row_width=1)
        for idx, skin in enumerate(matches):
            label = skin["market_hash_name"]
            callback_data = f"history_skin_{idx}"  # použij index
            keyboard.add(InlineKeyboardButton(text=label, callback_data=callback_data))

        try:
            self.bot.send_message(message.chat.id, "Select skin:", reply_markup=keyboard)
        except Exception as e:
            self.bot.send_message(message.chat.id, "Too many results please try again.")
            self.bot.register_next_step_handler(message, self.ask_skin_history_reply)
            print(e)

    def callback_history_skin(self, call):
        chat_id = call.message.chat.id
        idx = int(call.data.split("_")[-1])

        matches = self.user_skin_history_matches.get(chat_id, [])
        if idx >= len(matches):
            self.bot.send_message(chat_id, "Invalid selection.")
            return

        skin = matches[idx]
        skin_name = skin["market_hash_name"]
        history_data = next((item for item in self.skins.skins_history_data if item["market_hash_name"] == skin_name),
                            None)

        if not history_data:
            self.bot.send_message(chat_id, "No historical data available for this skin.")
            return

        market_url = history_data.get("item_page", "#")
        skin_name_html = escape(skin_name)
        skin_link = f'<a href="{market_url}">{skin_name_html}</a>'

        def stats_text(period, stats):
            return (
                f"{period}:\n"
                f"  Min: {stats.get('min', 'N/A')} EUR\n"
                f"  Max: {stats.get('max', 'N/A')} EUR\n"
                f"  Avg: {stats.get('avg', 'N/A')} EUR\n"
                f"  Median: {stats.get('median', 'N/A')} EUR\n"
                f"  Volume: {stats.get('volume', 'N/A')}\n"
            )

        text = f"📊 Price stats for {skin_link}:\n\n"
        text += stats_text("Last 24 hours", history_data.get("last_24_hours", {}))
        text += stats_text("\nLast 7 days", history_data.get("last_7_days", {}))
        text += stats_text("\nLast 30 days", history_data.get("last_30_days", {}))
        text += stats_text("\nLast 90 days", history_data.get("last_90_days", {}))

        self.bot.edit_message_text(chat_id=chat_id, message_id=call.message.message_id, text=text, parse_mode="HTML")

    # ------------- /remindskin HANDLER -------------
    @exit_guard
    def remindskin_start(self, message):
        self.bot.send_message(
            message.chat.id,
            "Please enter part of the skin name you want to be reminded about:"
        )
        self.bot.register_next_step_handler(message, self.remindskin_choose_skin)

    def remindskin_choose_skin(self, message):
        query = message.text.strip()
        matches = self.skins.find(query)
        print(f"DEBUG: User query: {query}, found matches: {[s['market_hash_name'] for s in matches]}")
        if not matches:
            self.bot.send_message(
                message.chat.id,
                "No skins found matching your input. Please try again with a different name."
            )
            return

        inline_kb = InlineKeyboardMarkup()
        for idx, skin in enumerate(matches):
            inline_kb.add(InlineKeyboardButton(
                skin["market_hash_name"],
                callback_data=f"remindskin_select_{idx}"
            ))
        self.user_remindskin_matches[message.chat.id] = matches
        self.bot.send_message(
            message.chat.id,
            "Choose the skin you want to be reminded about:",
            reply_markup=inline_kb
        )

    @exit_guard
    def remindskin_set_interval(self, message, matches):
        print ("interval")
        skin_name = message.text.strip()
        skin = next((s for s in matches if s["market_hash_name"] == skin_name), None)
        if not skin:
            self.bot.send_message(
                message.chat.id,
                "Invalid selection. Please start again with /remindskin."
            )
            return
        self.bot.send_message(
            message.chat.id,
            "How often do you want to be reminded? (e.g. 30 minutes, 2 hours, 1 day)"
        )
        self.bot.register_next_step_handler(message, self.remindskin_save, skin)

    @exit_guard
    def remindskin_save(self, message, skin=None):
        if skin is None:
            skin = getattr(self, "user_remindskin_pending", {}).pop(message.chat.id, None)
            if skin is None:
                self.bot.send_message(message.chat.id, "Something went wrong. Please try /remindskin again.")
                return

        text = message.text.strip().lower()
        interval_min = None
        if "hour" in text:
            num = ''.join([c for c in text if c.isdigit()])
            interval_min = int(num) * 60 if num else 60
        elif "day" in text:
            num = ''.join([c for c in text if c.isdigit()])
            interval_min = int(num) * 24 * 60 if num else 24 * 60
        elif "min" in text:
            num = ''.join([c for c in text if c.isdigit()])
            interval_min = int(num) if num else 1
        else:
            self.bot.send_message(
                message.chat.id,
                "Invalid interval. Please enter something like '30 minutes', '2 hours', or '1 day'."
            )
            self.bot.register_next_step_handler(message, self.remindskin_save, skin)
            return

        rid = self.db_insert_reminder.add_reminder(
            message.chat.id,
            skin["market_hash_name"],
            skin["item_page"],
            interval_min
        )

        stop_event = threading.Event()
        self.running_reminders[rid] = stop_event

        threading.Thread(
            target=self.reminder_loop,
            args=(message.chat.id, skin, interval_min, rid, stop_event),
            daemon=True
        ).start()

        self.bot.send_message(
            message.chat.id,
            f"Reminder set! Every {interval_min} minutes you will get a reminder for:\n"
            f"<a href=\"{skin['item_page']}\">{escape(skin['market_hash_name'])}</a>",
            parse_mode="HTML"
        )

    def reminder_loop(self, chat_id, skin, interval_min, reminder_id, stop_event):
        print(f"🔁 Starting reminder loop for {reminder_id} (every {interval_min} min)")
        while not stop_event.is_set():
            try:
                self.bot.send_message(
                    chat_id,
                    f"⏰ Reminder for skin:\n<a href='{skin['item_page']}'>{escape(skin['market_hash_name'])}</a>",
                    parse_mode="HTML"
                )
                for _ in range(interval_min * 60):
                    if stop_event.is_set():
                        print(f"🛑 Reminder loop for {reminder_id} received stop signal.")
                        return
                    time.sleep(1)
            except Exception as e:
                print(f"Reminder error for {reminder_id}: {e}")
                time.sleep(60)

    def start_reminders(self):
        self.running_reminders = {}
        reminders = self.db_select_reminder.get_all_reminders()
        for rem in reminders:
            skin = next((s for s in self.skins.skins if s["market_hash_name"] == rem["skin_market_hash_name"]), None)
            if skin:
                stop_event = threading.Event()
                self.running_reminders[rem["id"]] = stop_event  # ✅ Kritické!
                threading.Thread(
                    target=self.reminder_loop,
                    args=(rem["chat_id"], skin, rem["interval_minutes"], rem["id"], stop_event),
                    daemon=True
                ).start()
                print(f"🔁 Loaded reminder loop for {rem['id']} (every {rem['interval_minutes']} min)")


    def remindskin_inline_selected(self, call):
        idx = int(call.data.split("_")[-1])
        matches = self.user_remindskin_matches.get(call.message.chat.id, [])
        if idx >= len(matches):
            self.bot.send_message(call.message.chat.id, "Invalid selection. Please try again with /remindskin.")
            return

        skin = matches[idx]
        # Editujeme původní zprávu s klávesnicí, aby byla vidět potvrzená volba
        self.bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text=f"✅ Selected: {skin['market_hash_name']}\n\nHow often do you want to be reminded? (e.g. 30 minutes, 2 hours, 1 day)",
            reply_markup=None  # Odstraníme inline klávesnici
        )
        # Zaregistruj další krok pro tento chat
        self.bot.register_next_step_handler_by_chat_id(
            call.message.chat.id,
            lambda message: self.remindskin_interval_selected(message, skin)
        )
        self.bot.answer_callback_query(call.id)

    def remindskin_interval_selected(self, message, skin):
        interval_str = message.text.strip()
        try:
            interval_minutes = self.parse_interval(interval_str)
            rid = self.db_insert_reminder.add_reminder(
                message.chat.id,
                skin["market_hash_name"],
                skin["item_page"],
                interval_minutes
            )

            stop_event = threading.Event()
            self.running_reminders[rid] = stop_event

            threading.Thread(
                target=self.reminder_loop,
                args=(message.chat.id, skin, interval_minutes, rid, stop_event),
                daemon=True
            ).start()

            self.bot.send_message(
                message.chat.id,
                f"Reminder for {skin['market_hash_name']} every {interval_minutes} minutes was set!"
            )
        except Exception as e:
            self.bot.send_message(message.chat.id, f"Error: {e}")

    def parse_interval(self, interval_str):
        # Jednoduchý parser pro "30 minutes", "2 hours", "1 day"
        import re
        interval_str = interval_str.lower()
        match = re.match(r"(\d+)\s*(minute|min|hour|day)s?", interval_str)
        if not match:
            raise ValueError("Invalid interval format. Use e.g. '30 minutes', '2 hours', '1 day'")
        value, unit = int(match.group(1)), match.group(2)
        if "min" in unit:
            return value
        elif "hour" in unit:
            return value * 60
        elif "day" in unit:
            return value * 60 * 24
        else:
            raise ValueError("Unknown time unit.")

    def list_user_reminders(self, message):
        reminders = self.db_select_reminder.get_user_reminders(message.chat.id)
        if not reminders:
            self.bot.send_message(message.chat.id, "You have no reminders set.")
        else:
            keyboard = InlineKeyboardMarkup(row_width=1)
            for rem in reminders:
                label = f"{rem['skin_market_hash_name']} ({rem['interval_minutes']} min)"
                callback_data = f"select_reminder_{rem['id']}"
                keyboard.add(InlineKeyboardButton(text=label, callback_data=callback_data))
            self.bot.send_message(message.chat.id, "Your reminders:", reply_markup=keyboard)

    def callback_reminder_selected(self, call):
        chat_id = call.message.chat.id
        reminder_id = int(call.data.split("_")[-1])
        reminders = self.db_select_reminder.get_user_reminders(chat_id)
        reminder = next((r for r in reminders if r['id'] == reminder_id), None)
        if not reminder:
            self.bot.answer_callback_query(call.id, "Reminder not found.")
            return
        keyboard = InlineKeyboardMarkup()
        keyboard.add(InlineKeyboardButton(text="🗑️ Delete", callback_data=f"delete_reminder_{reminder['id']}"))
        keyboard.add(InlineKeyboardButton(text="✏️ Change", callback_data=f"change_reminder_{reminder['id']}"))
        msg = (f"🔔 <a href='{reminder['skin_item_page']}'>{escape(reminder['skin_market_hash_name'])}</a>\n"
               f"⏰ Interval: {reminder['interval_minutes']} minutes")
        self.bot.edit_message_text(chat_id=chat_id,
                                   message_id=call.message.message_id,
                                   text=msg,
                                   parse_mode="HTML",
                                   reply_markup=keyboard)

    def callback_delete_reminder(self, call):
        reminder_id = int(call.data.split("_")[-1])
        stop_event = self.running_reminders.pop(reminder_id, None)
        if stop_event:
            stop_event.set()
        self.db_delete_reminder.delete_reminder(reminder_id)
        self.bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                   text="🗑️ Reminder has been deleted.")


    def callback_change_reminder(self, call):
        chat_id = call.message.chat.id
        reminder_id = int(call.data.split("_")[-1])
        self.user_watch_data[chat_id] = {"edit_reminder_id": reminder_id}
        self.bot.edit_message_text(
            chat_id=chat_id,
            message_id=call.message.message_id,
            text="✏️ Enter new interval (e.g. '30 minutes', '2 hours', '1 day'):"
        )
        self.bot.register_next_step_handler_by_chat_id(chat_id, self.handle_reminder_interval_change)

    @exit_guard
    def handle_reminder_interval_change(self, message):
        chat_id = message.chat.id
        reminder_id = self.user_watch_data.get(chat_id, {}).get("edit_reminder_id")
        if not reminder_id:
            self.bot.send_message(chat_id, "⚠️ Session expired. Please try again.")
            return

        try:
            new_interval = self.parse_interval(message.text.strip())
            reminders = self.db_select_reminder.get_user_reminders(chat_id)
            rem = next((r for r in reminders if r["id"] == reminder_id), None)
            if not rem:
                self.bot.send_message(chat_id, "⚠️ Reminder not found.")
                return

            # ✅ Stop old reminder thread
            stop_event = self.running_reminders.pop(reminder_id, None)
            if stop_event:
                stop_event.set()
                print(f"🛑 Stopped old reminder thread: {reminder_id}")
            else:
                print(f"⚠️ No stop_event found for reminder {reminder_id} in self.running_reminders")

            # ✅ Update interval in DB
            self.db_update_reminder.update_reminder(reminder_id, new_interval)

            # ✅ Start new reminder thread with updated interval
            skin = next((s for s in self.skins.skins if s["market_hash_name"] == rem["skin_market_hash_name"]), None)
            if skin:
                new_event = threading.Event()
                self.running_reminders[reminder_id] = new_event
                threading.Thread(
                    target=self.reminder_loop,
                    args=(chat_id, skin, new_interval, reminder_id, new_event),
                    daemon=True
                ).start()
                print(f"✅ Started new reminder thread: {reminder_id}, interval: {new_interval} minutes")

            self.bot.send_message(chat_id, f"✅ Interval updated to {new_interval} minutes.")
            del self.user_watch_data[chat_id]

        except Exception as e:
            self.bot.send_message(chat_id, f"❌ Error: {e}. Please try again.")
            self.bot.register_next_step_handler(message, self.handle_reminder_interval_change)

    def run(self):
        """
        Start the bot polling loop.
        """
        self.bot.infinity_polling()
# ---------- Main ----------
if __name__ == "__main__":
    """
    Main entry point. Loads skins and starts the bot.
    """
    skins = Skins()
    skins.start_auto_refresh(300)

    #print(skins.load_skins())
    bot = WatchBot(API_TOKEN, DB_PATH, skins)
    bot.run()
