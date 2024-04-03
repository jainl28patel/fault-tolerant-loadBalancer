import threading
import socket
from asyncio import run
import yaml
from pathlib import Path
import json
import subprocess
import sqlite3
from enum import Enum
from time import sleep 
# required
NODE_NAME = "node1"
NODE_IP='10.61.119.144'
MASTER_IP=""
HEARTBEAT_PORT=9000

# global variables
slave = None

'''
    {
        task_id: str,
        data: {
            type: str,
            response: str,
            action: str
        },
        host_ip: str,
        host_port: int
    }
'''

# Create a thread-local data container
mydata = threading.local()

def get_db():
    # Ensure a unique connection per thread
    if not hasattr(mydata, "conn"):
        mydata.conn = sqlite3.connect(f'task_{NODE_NAME}.db')
    return mydata.conn


class TaskType(Enum):
    BASH = 1
    PYTHON = 2
    PYTHON3 = 3
    UNDEFINED = 4

class NodeTaskQueue:
    dbname = ""
    def __init__(self, db_name: str) -> None:
        NodeTaskQueue.dbname = f'{db_name}'
        
        self.lock = threading.Lock()
        conn = get_db()
        c = conn.cursor()
        c.execute(f'''CREATE TABLE IF NOT EXISTS {NodeTaskQueue.dbname}
             (task_id text, data text, host_ip text, host_port int)''')
        c.execute(f'''CREATE UNIQUE INDEX IF NOT EXISTS task_id_index
             ON {NodeTaskQueue.dbname} (task_id)''')
        conn.commit()

    def add_task(self, task_id: str, data: str, host_ip: str, host_port: int):
        with self.lock:
            try:
                conn = get_db()
                c = conn.cursor()
                print(task_id)
                print(data)
                print(host_ip)
                print(host_port)
                c.execute(f"INSERT INTO {NodeTaskQueue.dbname} VALUES (?, ?, ?, ?)", (task_id, str(data), host_ip, host_port))
                conn.commit()
                
                print(self.get_task("1212"))
            except sqlite3.IntegrityError:
                return "Task already exists in the queue."

    def get_all_task(self):
        with self.lock:
            try:
                conn = get_db()
                c = conn.cursor()
                c.execute(f"SELECT data FROM {NodeTaskQueue.dbname}")
                return c.fetchall()
            except sqlite3.IntegrityError:
                return "Task does not exist in the queue."
    
    def get_task(self, task_id: str):
        with self.lock:
            try:
                # TODO: modify below to include host_ip, host_port
                # self.c.execute(f"SELECT data, host_ip, host_port FROM {NodeTaskQueue.dbname} WHERE task_id=?", (task_id,))
                conn = get_db()
                c = conn.cursor()
                c.execute(f"SELECT data FROM {NodeTaskQueue.dbname} WHERE task_id=?", (task_id,))
                res = c.fetchone()
                print("res: ",res) 
                return res[0]
            except sqlite3.IntegrityError:
                return "Task does not exist in the queue."
    
    def remove_task(self, task_id: str):
        with self.lock:
            try:
                conn = get_db()
                c = conn.cursor()
                c.execute(f"DELETE FROM {NodeTaskQueue.dbname} WHERE task_id=?", (task_id,))
                conn.commit()
            except sqlite3.IntegrityError:
                return "Task does not exist in the queue."

    def __del__(self):
        conn = get_db()
        conn.close()

class Slave:
    def __init__(self) -> None:
        self.name = NODE_NAME
        self.port = 0
        self.task = ""
        self.request_queue = NodeTaskQueue(f'task_{NODE_NAME}')

    def __init__(self, port: int, task: str) -> None:
        # TODO: add multiple tasks
        self.name = NODE_NAME
        self.port = port
        self.task = task
        self.request_queue = NodeTaskQueue(f'task_{NODE_NAME}')

    def get_port(self):
        return self.port
    
    def get_node_name(self):
        return self.name
    
    def get_task(self):
        return self.task
    
    def pop_task_id(self, task_id : str):
        self.request_queue.remove_task(task_id)
    
    def handle_request(self, data: str, host_ip: str, host_port: int):
        # parses data from client and stores in the queue
        res = json.loads(data)
        self.request_queue.add_task(res["task_id"],json.dumps(res["data"]),host_ip,host_port)
    
    def process_bash_task(self, action: str ):
        output = subprocess.check_output(action, shell=True)
        return output
    
    def process_task(self, task_id: str):
        task = json.loads(self.request_queue.get_task(task_id))
        print("task : ", task)
        task_type = None
        if task["type"] == "bash":
            task_type = TaskType.BASH
        elif task["type"] == "python":
            task_type = TaskType.PYTHON
        elif task["type"] == "python3":
            task_type = TaskType.PYTHON3
        else:
            task_type = TaskType.UNDEFINED
        
        if(task_type == TaskType.BASH):
            return self.process_bash_task(task["action"])
        
        return None

    def handle_data(self, data: str, host_ip: str, host_port: int):
        # either data from client or master
        res = json.loads(data)
        for key in res.keys():
            if key == "data":
                self.handle_request(data, host_ip, host_port)
                break
            elif key == "task":
                # master
                self.handle_task(int(res["task_id"]),res["task"],res["to_execute"])
                break
        
    def handle_task(self, task_id: str, task: str, to_execute: str):
        # handles the task given from the master
        # or pops it from queue
        if (int(to_execute) == 1):
            if (task == self.task):
                # TODO: Change this
                print(self.process_task(task_id))
            else:
                print(f"Task: {task} not supported.")
        
        # pop the task_id
        self.pop_task_id(task_id)
        
        
def load_config():
    # load yaml
    global slave,MASTER_IP,HEARTBEAT_PORT
    config_path = Path("config.yaml")
    if not config_path.exists():
        print("config.yaml not found.") 
        return
    with open('config.yaml') as file:
        config = yaml.full_load(file)
        MASTER_IP = config["master"]["ip"]
        HEARTBEAT_PORT = config["heartbeat-port"]
        for node in config["nodes"]:
            node_name = next(iter(node))
            if(node_name == NODE_NAME):
                port = int(node[node_name]["port"])
                task = node[node_name]["task"]
                slave = Slave(port=port,task=task) 
                break
        else:
            print("NODE_NAME: {} not found in the config.yaml".format(NODE_NAME))
            return 0
    
    return 1

    
def slave_server():
    global slave
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((NODE_IP, slave.get_port())) 
    server.listen(5)
    print("started listening on: ", slave.get_port())

    while True:
        conn, addr = server.accept()
        data = conn.recv(1024)
        host, port = conn.getpeername()
        print(f"recieved from ip: {host} port: {port}")
        print(data)
        slave.handle_data(data,host,port)
        
        conn.close()

def start_health():
    while True:
        try:
            heartbeat = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            heartbeat.connect((MASTER_IP, HEARTBEAT_PORT))
            heartbeat.sendall(b'{"status":"up"}')
            heartbeat.close()
        except:
            pass
        sleep(15)
        

def main():
    if not load_config():
        return
      
    slave_server_thread = threading.Thread(target=slave_server)
    start_health_thread = threading.Thread(target=start_health)

    slave_server_thread.start()
    start_health_thread.start()
    
    slave_server_thread.join()
    start_health_thread.join()

if __name__ == "__main__":
    main()