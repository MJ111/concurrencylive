import enum
import functools
import heapq
import select
import socket
import time
from collections import deque
from typing import Tuple, TypeVar, Deque, Dict, Union, List

Task = TypeVar('Task')  # coroutine that await "Can"


async def algorithm(value: int) -> int:
    await async_sleep(10)
    return value + 42


Address = Tuple[str, int]


async def handler(client: socket.socket) -> None:
    while True:
        request: bytes = await async_recv(client, 100)
        # 100 byte 까지 받음. 그러나 0~100 범위. 그러나 보통은 http level에서 추상화되어있음.
        if not request:
            client.close()
            return
        response = await algorithm(int(request))
        await async_send(client, f'{response}\n'.encode('ascii'))


class Action(enum.Enum):
    WRITE = enum.auto()
    READ = enum.auto()
    WAKEUP = enum.auto()


class Can:
    def __init__(self, action: Action, target: Union[socket.socket, float]):
        self.action = action
        self.target = target

    def __await__(self):
        yield self.action, self.target


async def async_sleep(duration: float) -> None:
    await Can(Action.WAKEUP, duration)
    return


async def async_send(sock: socket.socket, data: bytes) -> int:
    await Can(Action.WRITE, sock)
    return sock.send(data)


async def async_recv(sock: socket.socket, num: int) -> bytes:
    await Can(Action.READ, sock)
    return sock.recv(num)


async def async_accept(sock: socket.socket) -> Tuple[socket.socket, Address]:
    await Can(Action.READ, sock)
    return sock.accept()


@functools.total_ordering  # it, eq로 다른 operator도 자동으로 정의해줌.
class TimerHandle:
    def __init__(self, task: Task, due: float):
        self.task = task
        self.due = due

    # c++ 처럼 operator overring이 가능함.
    def __lt__(self, other):  # less than
        return self.due < other.due

    def __eq__(self, other):  # equal
        return self.due == other.due


TASKS: Deque[Task] = deque()
WAIT_READ: Dict[socket.socket, Task] = {}
WAIT_WRITE: Dict[socket.socket, Task] = {}
WAIT_WAKEUP: List[TimerHandle] = []

MAX_TIMEOUT = 24 * 3600  # select에서 timeout이 너무 크면 처리를 못함.


def add_task(task: Task) -> None:
    TASKS.append(task)


def run_tasks() -> None:
    while any((TASKS, WAIT_WRITE, WAIT_READ, WAIT_WAKEUP)):
        now = time.monotonic()  # 단조 증가. summertime, 윤초 등 무시. 상대 시간을 계산하려고

        # select OS function
        while not TASKS:
            # OS function: select.select(rlist, wlist, xlist, timeout)
            # 현재 사용할 수 있는 socket을 기다림.
            # select가 깨워주는 순서에 따라서 multiplexing이 됨
            if WAIT_WAKEUP:
                timeout = max(0, int(WAIT_WAKEUP[0].due - now))
                timeout = min(MAX_TIMEOUT, timeout)
            else:
                timeout = MAX_TIMEOUT

            readables, writables, _ = select.select(WAIT_READ, WAIT_WRITE, [], timeout)
            now = time.monotonic()
            for sock in readables:
                add_task(WAIT_READ.pop(sock))
            for sock in writables:
                add_task(WAIT_WRITE.pop(sock))
            while WAIT_WAKEUP:
                timer_handle = WAIT_WAKEUP[0]
                if timer_handle.due >= now:
                    break
                add_task(timer_handle.task)
                heapq.heappop(WAIT_WAKEUP)
        current_task = TASKS.popleft()
        try:
            action, target = current_task.send(None)
        except StopIteration:
            continue

        if action is Action.READ:
            WAIT_READ[target] = current_task
        elif action is Action.WRITE:
            WAIT_WRITE[target] = current_task
        elif action is Action.WAKEUP:
            heapq.heappush(WAIT_WAKEUP, TimerHandle(current_task, now + target))
        else:
            raise RuntimeError(f'Unexpected action {action!r}')


async def server(address: Address) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # 소켓이 끊어졌을때 클라이언트가 다시 접속하면 끊어진 소켓을 다시 이어서 사용한다는 설정
    sock.bind(address)
    sock.listen(5)  # 소켓을 받는 queue의 길이. 보통 5~10 사용.

    while True:
        client, client_addr = await async_accept(sock)
        add_task(handler(client))  # 여기가 await이 아닌 이유는 I/O가 아니기 때문. await하면 기존 sync와 같이 블락됨.


if __name__ == '__main__':
    add_task(server(('127.0.0.1', 30303)))
    run_tasks()

"""
network server를 확장할때 thread, process 등등.. 우리는 async로 확장할 것임
python에서 corountine이 한 번도 실행되지 않고 gc되면 warning을 띄워줌.
ipython
- ipython에서 _는 마지막 리턴된 값

network는 client가 데이터를 얼마나 보낼지 모르기때문에 generator가 network를 구현하기에 좋음
generator는 stopiteration이 될때까지 무한히 돔

corountine, generator yield, yield from
send method

yield from 이 async/await 으로 바뀐 이유:
- async def 로 정의하면 아무것도 yield 하지 않는 coroutine을 만들 수 있음
- generator 안에서 await을 할 수 있음

@asyncio.corountine이 그걸 구현했다가 이젠 async def native로 쓸 수 있음

async def는 근본적으로 generator고 native로 쓸 수 있음  

deque는 양쪽 끝에서 아이템을 보통 리스트보다 굉장히 빨리 뺼수있는

과제: 클라이언트 요청을 sleep으로 throttling 걸기. 그러나 sleep을 동기적으로 하기 때문에 10초 sleep걸면 다음 클라이언트는 20초를 기다려야함.

socket은 운영체제에서 비동기로 처리하는 부분이 있음.

slect의 timeout으로 sleep.

heapq로 timer 정렬. O(logN)

sleep말고 다른 것들은 Can으로 어떻게 구현할까? asyncio 소스코드를 보면 됨.

run_until_complete는 run_tasks

task는 task와 동일

future는 can을 일반화한 것

task와 future의 차이는 future는 상태가 완료됐는지 안됐는지 상태를 들고 있고 task는 여러개를 처리할 수 있음.
task는 future를 상속.

cancellation도 있음.

call_soon, call_later 등은 자체적인 callback list가 있음. WAKEUP list와 비슷한.

unix-like 만 지원하는 trio trio async library도 있음.
"""
