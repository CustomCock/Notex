"""Erzeugt tests/fixtures/beispiel_traffic.pcap mit den in Block L4 festgelegten Sollwerten."""
from __future__ import annotations
import socket, struct, sys
from pathlib import Path
import dpkt

ETH_C = b"\x02\x00\x00\x00\x00\x10"   # Client 192.168.10.20
ETH_G = b"\x02\x00\x00\x00\x00\x01"   # Gateway 192.168.10.1
IP_C, IP_G = "192.168.10.20", "192.168.10.1"
DNS_SRV, WEB = "192.0.2.53", "198.51.100.25"

def eth(src, dst, data):
    f = dpkt.ethernet.Ethernet(src=src, dst=dst, data=data)
    if isinstance(data, dpkt.arp.ARP): f.type = dpkt.ethernet.ETH_TYPE_ARP
    return bytes(f)

def ip(src, dst, proto, data):
    p = dpkt.ip.IP(src=socket.inet_aton(src), dst=socket.inet_aton(dst), p=proto, data=data, ttl=64)
    p.len = len(p); return p

def arp(op, sha, spa, tha, tpa):
    return dpkt.arp.ARP(op=op, sha=sha, spa=socket.inet_aton(spa), tha=tha, spa_len=4,
                        tpa=socket.inet_aton(tpa))

def icmp(kind, ident, seq, data):
    e = dpkt.icmp.ICMP.Echo(id=ident, seq=seq, data=data)
    return dpkt.icmp.ICMP(type=kind, data=e)

def dns_q():
    q = dpkt.dns.DNS(id=0x1a2b, rd=1, qd=[dpkt.dns.DNS.Q(name="example.test", type=dpkt.dns.DNS_A)])
    return bytes(q)

def dns_a():
    an = dpkt.dns.DNS.RR(name="example.test", type=dpkt.dns.DNS_A, ttl=300, rlen=4, ip=socket.inet_aton(WEB))
    d = dpkt.dns.DNS(id=0x1a2b, qr=1, rd=1, ra=1, rcode=0,
                     qd=[dpkt.dns.DNS.Q(name="example.test", type=dpkt.dns.DNS_A)], an=[an])
    return bytes(d)

def tcp(sport, dport, seq, ack, flags, data=b""):
    return dpkt.tcp.TCP(sport=sport, dport=dport, seq=seq, ack=ack, flags=flags, off=5, win=64240, data=data)

GET = (b"GET /demo HTTP/1.1\r\nHost: example.test\r\nUser-Agent: PCAP-Demo/1.0\r\nConnection: close\r\n\r\n")
BODY = b"Hallo, das ist der PCAP-Body\n"
assert len(BODY) == 29, len(BODY)
RESP = (b"HTTP/1.1 200 OK\r\nContent-Type: text/plain; charset=utf-8\r\nContent-Length: 29\r\n"
        b"Connection: close\r\n\r\n" + BODY)
assert len(GET) == 88, len(GET)
assert len(RESP) == 128, len(RESP)

CP, WP = 49152, 80
pkts = []
def add(ts, raw): pkts.append((ts, raw))

add(0.000, eth(ETH_C, b"\xff\xff\xff\xff\xff\xff", arp(dpkt.arp.ARP_OP_REQUEST, ETH_C, IP_C, b"\x00"*6, IP_G)))
add(0.0005, eth(ETH_G, ETH_C, arp(dpkt.arp.ARP_OP_REPLY, ETH_G, IP_G, ETH_C, IP_C)))
add(1.000, eth(ETH_C, ETH_G, ip(IP_C, IP_G, dpkt.ip.IP_PROTO_ICMP, icmp(dpkt.icmp.ICMP_ECHO, 0x1234, 1, b"\x00"*18))))
add(2.001, eth(ETH_G, ETH_C, ip(IP_G, IP_C, dpkt.ip.IP_PROTO_ICMP, icmp(dpkt.icmp.ICMP_ECHOREPLY, 0x1234, 1, b"\x00"*18))))
add(3.000, eth(ETH_C, ETH_G, ip(IP_C, DNS_SRV, dpkt.ip.IP_PROTO_UDP, dpkt.udp.UDP(sport=53000, dport=53, data=dns_q(), ulen=8+len(dns_q())))))
add(4.001, eth(ETH_G, ETH_C, ip(DNS_SRV, IP_C, dpkt.ip.IP_PROTO_UDP, dpkt.udp.UDP(sport=53, dport=53000, data=dns_a(), ulen=8+len(dns_a())))))
add(5.000, eth(ETH_C, ETH_G, ip(IP_C, WEB, dpkt.ip.IP_PROTO_TCP, tcp(CP, WP, 1000, 0, dpkt.tcp.TH_SYN))))
add(5.010, eth(ETH_G, ETH_C, ip(WEB, IP_C, dpkt.ip.IP_PROTO_TCP, tcp(WP, CP, 5000, 1001, dpkt.tcp.TH_SYN|dpkt.tcp.TH_ACK))))
add(5.020, eth(ETH_C, ETH_G, ip(IP_C, WEB, dpkt.ip.IP_PROTO_TCP, tcp(CP, WP, 1001, 5001, dpkt.tcp.TH_ACK))))
add(5.030, eth(ETH_C, ETH_G, ip(IP_C, WEB, dpkt.ip.IP_PROTO_TCP, tcp(CP, WP, 1001, 5001, dpkt.tcp.TH_PUSH|dpkt.tcp.TH_ACK, GET))))
add(5.500, eth(ETH_G, ETH_C, ip(WEB, IP_C, dpkt.ip.IP_PROTO_TCP, tcp(WP, CP, 5001, 1001+len(GET), dpkt.tcp.TH_PUSH|dpkt.tcp.TH_ACK, RESP))))
add(5.600, eth(ETH_C, ETH_G, ip(IP_C, WEB, dpkt.ip.IP_PROTO_TCP, tcp(CP, WP, 1001+len(GET), 5001+len(RESP), dpkt.tcp.TH_FIN|dpkt.tcp.TH_ACK))))
add(5.610, eth(ETH_G, ETH_C, ip(WEB, IP_C, dpkt.ip.IP_PROTO_TCP, tcp(WP, CP, 5001+len(RESP), 1002+len(GET), dpkt.tcp.TH_FIN|dpkt.tcp.TH_ACK))))

out = Path("tests/fixtures/beispiel_traffic.pcap")
with open(out, "wb") as fh:
    writer = dpkt.pcap.Writer(fh)
    for ts, raw in pkts:
        writer.writepkt(raw, ts=1_700_000_000 + ts)
total = sum(len(raw) for _t, raw in pkts)
print(f"{len(pkts)} Pakete, {total} Bytes -> {out}")
