# Created by minjeongkim on 19/10/2018.
# code from Artisanal Async Adventures - PyCon APAC 2018 https://www.youtube.com/watch?v=IbwirUn9ubA
import select
from collections import deque

import socket
from enum import Enum, auto
from typing import Tuple, TypeVar, Deque, Dict


def algorithm(n: int) -> int:
    return n + 2


Address = Tuple[str, int]  # ip, port


async def handler(client: socket.socket) -> None:
    # blocked in here until connection is close
    # use instead thread or I/O multiplexing
    while True:
        # request = client.recv(100) # block until recv
        request: bytes = await async_recv(client, 100)

        if not request.strip():
            client.close()
            return
        number = int(request)
        result = algorithm(number)

        # client.send(f'{result}\n'.encode('ascii')) # block until send
        await async_send(client, f'{result}\n'.encode('ascii'))


async def server(address: Address) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(address)
    sock.listen(5)
    while True:
        # client, addr = sock.accept()  # block until connection
        client, addr = await async_accept(sock)
        print(f'Connection from {addr}')
        # handler(client)
        add_task(handler(client))


class Action(Enum):
    Read = auto()
    Send = auto()


class Can:
    def __init__(self, action: Action, target: socket.socket):
        self.action = action
        self.target = target

    def __await__(self):
        yield self.action, self.target


# signal want to read/send on sock
async def async_accept(sock: socket.socket) -> Tuple[socket.socket, Address]:
    await Can(Action.Read, sock)  # wait until we can read on socket
    return sock.accept()


async def async_recv(sock: socket.socket, num: int) -> bytes:
    await Can(Action.Read, sock)  # wait until we can read on socket
    return sock.recv(num)


async def async_send(sock: socket.socket, data: bytes) -> int:
    await Can(Action.Send, sock)  # wait until we can send on socket
    return sock.send(data)


Task = TypeVar('Task')
TASKS: Deque[Task] = deque()  # queue that can pop and append either side

# waiting area
WAIT_READ: Dict[socket.socket, Task] = {}
WAIT_SEND: Dict[socket.socket, Task] = {}


def add_task(task: Task) -> None:
    TASKS.append(task)


def run() -> None:
    # core of event loop. run tasks
    while any([TASKS, WAIT_SEND, WAIT_READ]):
        while not TASKS:
            can_read, can_send, _ = select.select(WAIT_READ, WAIT_SEND, [])
            for sock in can_read:
                add_task(WAIT_READ.pop(sock))
            for sock in can_send:
                add_task(WAIT_SEND.pop(sock))

        current_task = TASKS.popleft()
        try:
            action, target = current_task.send(None)  # execute stopped async method
        except StopIteration:
            # means this task is done
            continue

        if action is Action.Read:
            WAIT_READ[target] = current_task
        elif action is Action.Send:
            WAIT_SEND[target] = current_task
        else:
            raise ValueError(f'Unexpected action {action}')


# server('localhost', 30303)
add_task(server(('localhost', 30303)))
run()

"""
homework:
- instead using select, use epoll, kqueue, etc..
- add sleep method
"""
