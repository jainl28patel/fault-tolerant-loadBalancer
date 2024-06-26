import socket
import json
import asyncio
from flask import Flask, request, jsonify

app = Flask(__name__)


def request_parser(request):
    if isinstance(request, dict):
        task = request["task"]
        task_id = request["task_id"]
    else:
        try:
            task = (json.loads(request))["task"]
            task_id = (json.loads(request))["task_id"]
        except TypeError:
            print("The request must be a dictionary or a JSON-formatted string.")
            return None, None
    return (task, task_id)


async def send_data_to_socket(url, data):
    host, port = url.split(":")
    reader, writer = await asyncio.open_connection(host, int(port))
    writer.write(data.encode())
    await writer.drain()
    response = await reader.read(100)
    writer.close()
    await writer.wait_closed()
    return response


@app.route("/", methods=["GET"])
def user_get_request():
    tasks = [send_data_to_socket(node_url, "GET") for node_url in node_urls]
    node_responses = asyncio.run(asyncio.gather(*tasks))
    return jsonify([response.decode() for response in node_responses]), 200


@app.route("/", methods=["POST"])
async def user_post_request():
    request_data = request.get_json()
    task, task_id = request_parser(request_data)
    await send_data_to_socket(
        master_url, json.dumps({"task": task, "task_id": task_id})
    )
    tasks = [
        asyncio.create_task(send_data_to_socket(node_url, json.dumps(request_data)))
        for node_url in node_urls
    ]
    for task in asyncio.as_completed(tasks):
        response = await task
        response_data = json.loads(response.decode())
        if response_data.get("status") == "yes":
            for t in tasks:
                t.cancel()  # cancel all other tasks
            return jsonify(response_data), 200
    return jsonify({"message": "Task cannot be performed"}), 500


node_urls = ["localhost:8080"]  # "localhost:8082", "localhost:8083", "localhost:8084"]
master_url = "localhost:8000"

if __name__ == "__main__":
    app.run(port=80)
