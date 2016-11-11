import multiprocessing
import traceback


class LogExceptions(object):
    def __init__(self, callable):
        self.__callable = callable
        return

    def __call__(self, *args, **kwargs):
        try:
            result = self.__callable(*args, **kwargs)

        except Exception:
            print(traceback.format_exc())
            raise

        return result


def doParallel(func, items, *args, **kwargs):
    pool = multiprocessing.Pool(processes=None)
    results = []

    try:
        for item in items:
            if isinstance(item, str):
                argument = [item] + list(args)
            else:
                argument = list(item) + list(args)
            results.append(pool.apply_async(LogExceptions(func), argument, kwargs))
        pool.close()
        pool.join()

        for result in results:
            result.get()

    except (KeyboardInterrupt, Exception):
        pool.terminate()
        pool.join()
        raise


def doPlatformParallel(func, platforms, *args, **kwargs):
    pool = multiprocessing.Pool(processes=None)
    results = dict()
    output = dict()

    try:
        for platform in platforms:
            argument = [platform] + list(args)
            results[platform] = pool.apply_async(LogExceptions(func), argument, kwargs)
        pool.close()
        pool.join()

        for item in results:
            output[item] = results[item].get()

    except (KeyboardInterrupt, Exception):
        pool.terminate()
        pool.join()
        raise

    return output


def parallelDict(dict):
    pool = multiprocessing.Pool(processes=multiprocessing.cpu_count())
    results = []
    output = []

    try:
        for func in dict:
            for item in dict[func]:
                results.append(pool.apply_async(LogExceptions(func), list(item)))
        pool.close()
        pool.join()

        for result in results:
            ret = result.get()
            if ret:
                output.append(ret)
    except (KeyboardInterrupt, Exception):
        pool.terminate()
        pool.join()
        raise

    return output
