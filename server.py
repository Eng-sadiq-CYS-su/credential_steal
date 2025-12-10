import socket
import threading
import os
from datetime import datetime


class ImprovedServer:
    def __init__(self, host='0.0.0.0', port=5555):
        self.host = host
        self.port = port
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.clients = []

    def start(self):
        try:
            self.socket.bind((self.host, self.port))
            self.socket.listen(5)
            print(f"[+] Server listening on {self.host}:{self.port}")
            print(f"[+] Create a folder named 'collected_data' to save results")

            while True:
                client_socket, client_address = self.socket.accept()
                print(f"[+] Connection from {client_address}")
                self.clients.append(client_socket)

                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client_socket, client_address)
                )
                client_thread.daemon = True
                client_thread.start()

        except Exception as e:
            print(f"[-] Error: {e}")
        finally:
            self.socket.close()

    def handle_client(self, client_socket, client_address):
        try:
            data = b""
            while True:
                chunk = client_socket.recv(4096)
                if not chunk:
                    break
                data += chunk

            if data:
                self.save_data(data, client_address)
                print(f"[+] Received {len(data)} bytes from {client_address}")

        except Exception as e:
            print(f"[-] Error with client {client_address}: {e}")
        finally:
            client_socket.close()
            if client_socket in self.clients:
                self.clients.remove(client_socket)

    def save_data(self, data, client_address):
        # إنشاء مجلد للبيانات إذا لم يكن موجوداً
        if not os.path.exists("collected_data"):
            os.makedirs("collected_data")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"collected_data/data_{client_address[0]}_{timestamp}.txt"

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(data.decode('utf-8'))
            print(f"[+] Data saved to {filename}")
        except UnicodeDecodeError:
            with open(filename, 'wb') as f:
                f.write(data)
            print(f"[+] Binary data saved to {filename}")


if __name__ == "__main__":
    server = ImprovedServer()
    server.start()