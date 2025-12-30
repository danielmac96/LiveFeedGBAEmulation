import socket
import time
import sys

# Update this to match the port shown in your mGBA console
PORT = 8888
HOST = "127.0.0.1"


def start_controller():
    try:
        # Create a persistent connection
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(5)
            print(f"Connecting to mGBA on {HOST}:{PORT}...")
            s.connect((HOST, PORT))
            print("Connected! Commands: A, B, s (select), S (start), <, >, ^, v, L, R")
            print("Type 'exit' to quit.\n")

            while True:
                # Get manual input from you in the PyCharm terminal
                command = input("Enter Button: ").strip()

                if command.lower() == 'exit':
                    break

                if not command:
                    continue

                # The Lua script uses sock:receive(1024)
                # We add \n to ensure the message is 'finished'
                message = command + "\n"
                s.sendall(message.encode())
                print(f"Sent: {command}")
                time.sleep(0.1)  # Gives mGBA 6 frames to process the last input

                # Optional: Listen to the key-state broadcast coming back from mGBA
                # data = s.recv(1024)
                # print(f"mGBA State: {data.decode().strip()}")

    except ConnectionRefusedError:
        print("Error: mGBA refused the connection. Is the script running?")
    except Exception as e:
        print(f"An error occurred: {e}")


if __name__ == "__main__":
    start_controller()