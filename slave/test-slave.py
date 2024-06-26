import socket

def send_hello(address, port):
    # Create a socket object
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        # Connect to the server
        s.connect((address, port))
        
        # Send "hello" message
        s.sendall(b'{"task_id":"1212", "data": {"search_text": "heyyyy"}}')
        
        # Receive the response from the server, if you expect one
        data = s.recv(1024)
        
        # Print the response from the server
        print('Received', repr(data))

# Example usage
address = '10.81.49.125'  # Replace 'example.com' with the actual address
port = 6969  # Replace 12345 with the actua l port number

send_hello(address, port)
