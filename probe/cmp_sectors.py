import subprocess
def disc_sector(n):
    out = subprocess.run(["dd","if=/dev/sr0","bs=2048","skip="+str(n),"count=1","status=none"], capture_output=True)
    return out.stdout
f = open("/home/carrot/muse/disc-probe/iso/random.iso","rb")
def iso_sector(n):
    f.seek(n*2048); return f.read(2048)
tests = [(0,0),(150,0),(0,150),(2295103,2295103),(2295253,2295103),(300,150)]
for dn, inum in tests:
    d = disc_sector(dn); i = iso_sector(inum)
    tag = "SAME" if d == i else "DIFF"
    print("disc[%d] vs iso[%d]: %s disc_head=%s iso_head=%s" % (dn, inum, tag, d[:8].hex(), i[:8].hex()))
