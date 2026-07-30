from collections import deque

# guarda últimos 200 logs
log_buffer = deque(maxlen=200)


def add_log(message):
    log_buffer.append(message)


def get_logs():
    return list(log_buffer)
