import threading
import socket
import heart_beat
from asyncio import run
import yaml
from pathlib import Path
import json 
from heart_beat import nodes_health

class Node:
    def __init__(self) -> None:
        self.node = []
        self.lock = threading.Lock()

    def __str__(self) -> str:
        with self.lock:
            return json.dumps(self.node, indent=4)

    def add(self, node):
        with self.lock:
            self.node.append(node)
    
    def get_task_node_ip(self, task):
        with self.lock:
            ret = []
            for node in self.node:
                name = next(iter(node))
                if task in node[name]["task"]:
                    ret.append(node[name]["ip"])
            return ret
        
    def get_task_list(self):
        with self.lock:
            ret = set()
            for node in self.node:
                name = next(iter(node))
                ret.add(node[name]["task"])
            return ret
        
    def get_all_ip(self):
        with self.lock:
            ret = []
            for node in self.node:
                name = next(iter(node))
                ret.append(node[name]["ip"])
            return ret

class RoundRobin:
    def __init__(self, node_list: Node) -> None:
        self.task_to_ip = {}
        self.last_task_ip = {}

        for task in node_list.get_task_list():
            self.task_to_ip[task] = []
            for ip in node_list.get_task_node_ip(task):
                self.task_to_ip[task].append(ip)
            self.last_task_ip[task] = 0

        self.lock = threading.Lock()

    def get_ip(self, task):
        with self.lock:
            ip = self.task_to_ip[task][self.last_task_ip[task]]
            self.last_task_ip[task] = (self.last_task_ip[task] + 1) % len(self.task_to_ip[task])
            return ip

def load_config():
    # load yaml
    config_path = Path("config.yaml")
    if not config_path.exists():
        print("config.yaml not found.") 
        return
    with open('config.yaml') as file:
        config = yaml.full_load(file)
        for node in config["nodes"]:
            NODE.add(node)

def handle_request(data):
    """
    Tentative data format:
        {
            "task": "task_name",
            "task_id": "task_id",
        }
    """

    data = json.loads(data)
    task = data["task"]
    task_id = data["task_id"]
    data["to_execute"] = False

    ip_dest = RR.get_ip(task)
    ip_list = NODE.get_all_ip()

    # Send task to node
    for ip in ip_list:
        if ip == ip_dest:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((ip, 8000)) # later change to node IP as per yaml file
            data["to_execute"] = True
            sock.sendall(json.dumps(data).encode())
            sock.close()
        else:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((ip, 8000)) # later change to node IP as per yaml file
            sock.sendall(json.dumps(data).encode())
            sock.close()

def server():
    # Listen for incoming headers and send to respective nodes or stores in queue
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(('localhost', 8000))    # later change to master node IP as per yaml file
    server.listen(5)

    # handle incoming requests using different threads
    while True:
        conn, addr = server.accept()
        data = conn.recv(1024).decode()
        threading.Thread(target=handle_request, args=(data,)).start()

def heartbeat():
    # responsible_node_url = "http://127.0.0.1:5000/report"
    # node_urls = [
    #     "https://github.com/iiteen",
    #     "https://github.com/wadetb/heartbeat",
    #     "http://127.0.0.1:80/",
    #     # Add more node URLs as needed
    # ]

    node_urls = []
    for ip in NODE.get_all_ip():
        node_urls.append(f"http://{ip}/report")

    print(node_urls)

    run(heart_beat.main(node_urls))


def main():
    global NODE, RR
    NODE = Node()
    load_config()
    RR = RoundRobin(NODE)
    
    server_thread = threading.Thread(target=server)
    heartbeat_thread = threading.Thread(target=heartbeat)

    server_thread.start()
    heartbeat_thread.start()

    server_thread.join()
    heartbeat_thread.join()


# Global variables
# Node health imported from heart_beat.py
NODE = None
RR = None

if __name__ == "__main__":
    main()