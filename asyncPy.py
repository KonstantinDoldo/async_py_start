# ------------------------------------------------------------------
# простой код без асинхронности

import socket

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(('localhost', 5001))
server_socket.listen()

while True:
    print('before accept()')
    client_socket, addr = server_socket.accept()
    print('connection from', addr)

    while True:
        request = client_socket.recv(1024)

        if not request:
            break
        else:
            response = 'Hello world\n'.encode()
            client_socket.send(response)

    print('outside inner while loop')
    client_socket.close()

# ------------------------------------------------------------------

# - использование event-loop-а

import socket
from select import select

to_monitor = []

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind(('localhost', 5001))
server_socket.listen()


def accept_connection(server_socket):
    client_socket, addr = server_socket.accept()
    print('connection from', addr)
    to_monitor.append(client_socket)


def send_message(client_socket):
    request = client_socket.recv(4096)
    if request:
        response = 'Hello world\n\n'.encode()
        client_socket.send(response)
    else:
        client_socket.close()


def event_loop():
    while True:
        ready_to_read, _, _ = select(to_monitor, [], [])
        for sock in ready_to_read:
            if sock is server_socket:
                accept_connection(sock)
            else:
                send_message(sock)


if __name__ == '__main__':
    to_monitor.append(server_socket)
    event_loop()

# ------------------------------------------------------------------

# ипользование селекторов

import socket
import selectors

selector = selectors.DefaultSelector()


def server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('localhost', 5001))
    server_socket.listen()
    selector.register(fileobj=server_socket, events=selectors.EVENT_READ, data=accept_connection)


def accept_connection(server_socket):
    client_socket, addr = server_socket.accept()
    print('connection from', addr)
    selector.register(fileobj=client_socket, events=selectors.EVENT_READ, data=send_message)


def send_message(client_socket):
    request = client_socket.recv(4096)
    if request:
        response = 'Hello world\n\n'.encode()
        client_socket.send(response)
    else:
        selector.unregister(client_socket)
        client_socket.close()


def event_loop():
    while True:
        events = selector.select()  # (key, events - bit mask of event: r or w)
        # print(events)
        for key, _ in events:
            callback = key.data
            callback(key.fileobj)


if __name__ == '__main__':
    server()
    event_loop()

#------------------------------------------------------------------

# аснихронность с ипользованием Генераторов - RoundRobin/Карусель

def gen1(s):
    for b in s:
        yield b


def gen2(n):
    for i in range(n):
        yield i


g1 = gen1('kosk')
g2 = gen2(4)
tasks = [g1, g2]

while tasks:
    task = tasks.pop(0)
    try:
        print(next(task))
        tasks.append(task)
    except StopIteration:
        pass

# ------------------------------------------------------------------

# асинхронность на Генераторах, пример Д.Бизли с PyCon'15

# "В коде два типа генераторов, один под серверный сокет, и второй под клиентские сокеты, т.е.под каждый
# клиентский сокет инициализируется свой клиентский генератор, связь идет через те словари. Yield он просто
# для регистрации сокета на чтение - запись для select. Как только селект заметит активность на каком то сокете,
# то далее код дернет соответствующий генератор(который через словарь сопоставлен сокету), он прокрутится
# и дальше снова слушаем сокеты через селект"

# "1. добваляем генератор server() в задачи
# 2. в event_loop() поскольку есть задача, мы получаем read, server_socket = next(task)
# в server()[т.е. task] мы вышли на первом yield и ждём следующего next
# 3. добавляем в словарь на мониторинг to_read[sock] = task[ждёт следующий next]
# 4. задачи закончились - переходим во внутренний while[пока что мониторим серверный сокет на чтение]
# 5. как только мы попытались установить соединение - отрабатывает selector,
# добавляющий в задачи генератор, ждущий следующего next() tasks.append(to_read.pop(sock))
# 6. выходим из внутреннего while, поскольку появилась новая задача
# 7. делаем второй read, server_socket = next(task)
# 7.1 принимаем соединение и создаём клиентский сокет: client_socket, addr = server_socket.accept()
# 7.2 добавляем клиентский генератор в задачи: tasks.append(client(client_socket))
# 7.3 опять добавляем server_socket в словарь на мониторинг to_read[sock] = task[ждёт следующий next]
# 8. первая задача закончилась - переходим ко второй - обработка генератора client(client_socket)
# 8.1. read, client_socket = next(task2)
# 8.2. добавляем в мониторинг на чтение to_read[sock] = task2[ждёт следующего next]
# 8.3. задачи закончились - входим во внутренний цикл - мониторим два сокета на чтение
# 9. отправляем сообщение со стороны клиента
# 10. отрабатывает selector и добавляет генератор client() в задачи tasks
# 11. выходим из внутреннего while
# 12. write, client_socket = next(task2) - теперь уже на запись
# 13. добавляем в мониторинг на запись to_write[sock] = task2
# 13. поскольку буфер свободен то сразу работает selector и отдаст генератор в задачи
# 14. отправляем сообщение,
# 15. смещаемся до следующего yield и опять добавляем клиентский сокет в мониторинг на чтение"

import socket
from select import select

tasks = []

to_read = {}
to_write = {}

def server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(('localhost', 5001))
    server_socket.listen()

    while True:
        yield ('read', server_socket)
        client_socket, addr = server_socket.accept()    # read

        print('connection from', addr)
        tasks.append(client(client_socket))


def client(client_socket):
    while True:

        yield ('read', client_socket)
        request = client_socket.recv(1024)  # read

        if not request:
            break
        else:
            response = 'Hello world\n'.encode()

            yield ('write', client_socket)
            client_socket.send(response)    # write

    client_socket.close()


def event_loop():
    while any([tasks, to_read, to_write]):
        if not tasks:
            ready_to_read, ready_to_write, _ = select(to_read, to_write, [])
            for sock in ready_to_read:
                tasks.append(to_read.pop(sock)) # возвращает значение ключа - сокет
            for sock in ready_to_write:
                tasks.append(to_write.pop(sock))
        try:
            task = tasks.pop(0)
            mode, socket = next(task)
            if mode == 'read':
                to_read[socket] = task
            if mode == 'write':
                to_write[socket] = task
        except StopIteration:
            print('no tasks/clients')

tasks.append(server())
event_loop()

# ------------------------------------------------------------------

# асинхронность на базе asyncio (~3.5) и вариант синтаксиса pre-3.5

import asyncio
from time import time

#@asyncio.coroutine
async def print_nums():
    num = 1
    while True:
        print(num)
        num+=1
        #yield from asyncio.sleep(0.1)
        await asyncio.sleep(0.1)

#@asyncio.coroutine
async def print_time():
    count = 0
    while True:
        if count % 3 == 0:
            print("{} seconds pass".format(count))
        count+=1
        # yield from asyncio.sleep(1)
        await asyncio.sleep(1)

#@asyncio.coroutine
async def main():
    # task1 = asyncio.ensure_future(print_nums())
    # task2 = asyncio.ensure_future(print_time())
    task1 = asyncio.create_task(print_nums())
    task2 = asyncio.create_task(print_time())

    await asyncio.gather(task1, task2)

if __name__ == '__main__':
    # loop = asyncio.get_event_loop()
    # loop.run_until_complete(main())
    # loop.close()
    asyncio.run(main())

# ------------------------------------------------------------------

# еще один простой событийного цикла и генераторов

from time import sleep

queue = []

def counter():
    i =0
    while True:
        print(i)
        i += 1
        yield


def printer():
    timer = 0
    while True:
        if timer % 9 == 0:
            print('test')
        timer += 1
        yield


def event_loop():
    while True:
        task = queue.pop(0)
        next(task)
        queue.append(task)
        sleep(0.25)


if __name__ == '__main__':
    counter = counter()
    printer = printer()
    queue.append(counter)
    queue.append(printer)
    event_loop()