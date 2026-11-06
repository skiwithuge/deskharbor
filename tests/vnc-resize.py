"""Authenticate to local VNC and request a desktop size (isolated smoke test only)."""
import socket, struct, subprocess, sys
width,height=map(int,sys.argv[1:])
password=open('/run/secrets/vnc_password','rb').read()[:8].ljust(8,b'\0')
key=bytes(int(f'{b:08b}'[::-1],2) for b in password)
s=socket.create_connection(('127.0.0.1',5901),timeout=5)
def read(n):
    data=b''
    while len(data)<n:
        part=s.recv(n-len(data))
        if not part: raise RuntimeError('VNC closed the connection')
        data+=part
    return data
assert read(12)==b'RFB 003.008\n'
s.sendall(b'RFB 003.008\n')
types=read(read(1)[0]); assert 2 in types,types
s.sendall(b'\x02')
challenge=read(16)
response=subprocess.check_output(['openssl','enc','-des-ecb','-provider','legacy','-provider','default','-K',key.hex(),'-nosalt','-nopad'],input=challenge)
s.sendall(response)
assert struct.unpack('>I',read(4))[0]==0,'VNC auth failed'
s.sendall(b'\x01')
header=read(24); read(struct.unpack('>I',header[20:])[0])
s.sendall(struct.pack('>BBHi',2,0,1,-308))
s.sendall(struct.pack('>BBHHBBIHHHHI',251,0,width,height,1,0,0,0,0,width,height,0))
# Keep the requesting client connected long enough for the server to process it.
import time
time.sleep(1)
s.close()
