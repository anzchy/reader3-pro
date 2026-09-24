import multiprocessing as mp, sys, time
def burn(deadline):
    while time.monotonic() < deadline:
        pass
if __name__ == "__main__":
    n, dur = int(sys.argv[1]), float(sys.argv[2])
    d = time.monotonic() + dur
    ps = [mp.Process(target=burn, args=(d,)) for _ in range(n)]
    for p in ps: p.start()
    for p in ps: p.join()
