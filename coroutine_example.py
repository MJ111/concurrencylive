# Created by minjeongkim on 19/10/2018.
async def bar():
    print('bar')


ret = bar()  # coroutine

ret.send(None)


# 'bar' printed
# StopIteration raised

class Foo:
    def __await__(self):
        yield 42


async def bar():
    await Foo()


ret = bar()  # corountine

ret.send(None)  # 42

ret.send(None)  # StopIteration
