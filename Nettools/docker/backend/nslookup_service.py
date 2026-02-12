"""
NetTools - NSLookup / DNS Lookup Service
Provides DNS resolution and record querying
"""

import subprocess
import re
import socket
import logging

logger = logging.getLogger(__name__)


def run_nslookup(domain: str, dns_server: str = None, record_type: str = "A") -> dict:
    """
    Run a DNS lookup for the specified domain.

    Args:
        domain: Domain name or IP address to look up
        dns_server: Optional DNS server to query (e.g., 8.8.8.8)
        record_type: DNS record type (A, AAAA, MX, NS, TXT, CNAME, SOA, PTR, SRV, ANY)

    Returns:
        dict with keys:
        - domain: original query
        - record_type: type queried
        - dns_server: server used
        - records: list of result records
        - query_time: time in ms
        - authoritative: whether response is authoritative
        - error: error message if failed
    """
    try:
        domain = domain.strip()
        if not domain:
            raise ValueError("El dominio está vacío")

        # Basic input sanitization
        if not re.match(r'^[a-zA-Z0-9\.\-:_]+$', domain):
            raise ValueError(f"Dominio no válido: {domain}")

        record_type = record_type.upper().strip()
        valid_types = ['A', 'AAAA', 'MX', 'NS', 'TXT', 'CNAME', 'SOA', 'PTR', 'SRV', 'ANY']
        if record_type not in valid_types:
            raise ValueError(f"Tipo de registro no válido: {record_type}")

        if dns_server:
            dns_server = dns_server.strip()
            if not re.match(r'^[a-zA-Z0-9\.\-:]+$', dns_server):
                raise ValueError(f"Servidor DNS no válido: {dns_server}")

        logger.info(f"NSLookup: {domain} type={record_type} server={dns_server or 'default'}")

        # Try using 'dig' first (more detailed), fall back to 'nslookup'
        try:
            return _run_dig(domain, dns_server, record_type)
        except FileNotFoundError:
            logger.warning("dig not found, trying nslookup...")
            return _run_nslookup_cmd(domain, dns_server, record_type)

    except ValueError as e:
        logger.error(f"NSLookup validation error: {e}")
        raise
    except Exception as e:
        logger.error(f"NSLookup error: {e}")
        raise


def _run_dig(domain: str, dns_server: str = None, record_type: str = "A") -> dict:
    """Run DNS lookup using dig command."""
    cmd = ['dig']

    if dns_server:
        cmd.append(f'@{dns_server}')

    cmd.extend([domain, record_type, '+noall', '+answer', '+authority', '+stats', '+question'])

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=15
    )

    output = result.stdout
    records = []
    query_time = None
    server_used = dns_server or 'Sistema'
    authoritative = False

    for line in output.strip().split('\n'):
        line = line.strip()

        # Parse query time
        time_match = re.search(r'Query time:\s*(\d+)\s*msec', line)
        if time_match:
            query_time = int(time_match.group(1))
            continue

        # Parse server used
        server_match = re.search(r'SERVER:\s*([^\s#]+)', line)
        if server_match:
            if not dns_server:
                server_used = server_match.group(1)
            continue

        # Check for authoritative
        if 'flags' in line.lower() and 'aa' in line.lower():
            authoritative = True
            continue

        # Skip comments and empty lines
        if line.startswith(';') or not line:
            continue

        # Parse answer records
        # Format: domain. TTL CLASS TYPE VALUE
        record_match = re.match(
            r'^(\S+)\s+(\d+)\s+IN\s+(\S+)\s+(.+)$', line
        )
        if record_match:
            rec_name = record_match.group(1).rstrip('.')
            rec_ttl = int(record_match.group(2))
            rec_type = record_match.group(3)
            rec_value = record_match.group(4).strip().rstrip('.')

            record = {
                'name': rec_name,
                'ttl': rec_ttl,
                'type': rec_type,
                'value': rec_value,
            }

            # Parse MX priority
            if rec_type == 'MX':
                mx_match = re.match(r'^(\d+)\s+(.+)$', rec_value)
                if mx_match:
                    record['priority'] = int(mx_match.group(1))
                    record['value'] = mx_match.group(2).rstrip('.')

            # Parse SOA fields
            if rec_type == 'SOA':
                soa_parts = rec_value.split()
                if len(soa_parts) >= 7:
                    record['primary_ns'] = soa_parts[0].rstrip('.')
                    record['admin_email'] = soa_parts[1].rstrip('.').replace('.', '@', 1)
                    record['serial'] = soa_parts[2]
                    record['refresh'] = soa_parts[3]
                    record['retry'] = soa_parts[4]
                    record['expire'] = soa_parts[5]
                    record['minimum_ttl'] = soa_parts[6]

            # Parse SRV fields
            if rec_type == 'SRV':
                srv_parts = rec_value.split()
                if len(srv_parts) >= 3:
                    record['priority'] = int(srv_parts[0]) if srv_parts[0].isdigit() else 0
                    record['weight'] = int(srv_parts[1]) if srv_parts[1].isdigit() else 0
                    record['port'] = int(srv_parts[2]) if srv_parts[2].isdigit() else 0
                    record['value'] = srv_parts[3].rstrip('.') if len(srv_parts) > 3 else rec_value

            records.append(record)

    # If no records found via dig answer section, try a basic Python resolution for A records
    if not records and record_type == 'A':
        records = _python_resolve(domain, record_type)

    return {
        'domain': domain,
        'record_type': record_type,
        'dns_server': server_used,
        'records': records,
        'query_time': query_time,
        'authoritative': authoritative,
        'error': None if records else 'No se encontraron registros',
    }


def _run_nslookup_cmd(domain: str, dns_server: str = None, record_type: str = "A") -> dict:
    """Fallback using nslookup command."""
    cmd = ['nslookup']

    if record_type != 'A':
        cmd.extend(['-type=' + record_type])

    cmd.append(domain)

    if dns_server:
        cmd.append(dns_server)

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=15
    )

    output = result.stdout + '\n' + result.stderr
    records = []
    server_used = dns_server or 'Sistema'
    authoritative = 'authoritative' in output.lower() and 'non-authoritative' not in output.lower()

    # Parse nslookup output
    in_answer = False
    for line in output.strip().split('\n'):
        line = line.strip()

        # Detect server
        server_match = re.match(r'^Server:\s*(.+)$', line)
        if server_match and not dns_server:
            server_used = server_match.group(1).strip()

        # Start of answer section
        if 'name:' in line.lower() or 'address:' in line.lower():
            in_answer = True

        # Parse A/AAAA records
        addr_match = re.match(r'^Address:\s*(\S+)$', line)
        if addr_match and in_answer:
            ip = addr_match.group(1)
            if not ip.startswith('#') and ':' not in ip.split('#')[0]:
                records.append({
                    'name': domain,
                    'ttl': None,
                    'type': 'A',
                    'value': ip.split('#')[0],
                })
            elif '::' in ip or ':' in ip:
                records.append({
                    'name': domain,
                    'ttl': None,
                    'type': 'AAAA',
                    'value': ip,
                })

        # Parse MX records
        mx_match = re.match(r'^.+mail exchanger\s*=\s*(\d+)\s+(.+)$', line, re.I)
        if mx_match:
            records.append({
                'name': domain,
                'ttl': None,
                'type': 'MX',
                'value': mx_match.group(2).strip().rstrip('.'),
                'priority': int(mx_match.group(1)),
            })

        # Parse NS records
        ns_match = re.match(r'^.+nameserver\s*=\s*(.+)$', line, re.I)
        if ns_match:
            records.append({
                'name': domain,
                'ttl': None,
                'type': 'NS',
                'value': ns_match.group(1).strip().rstrip('.'),
            })

        # Parse TXT records
        txt_match = re.match(r'^.+text\s*=\s*"(.+)"$', line, re.I)
        if txt_match:
            records.append({
                'name': domain,
                'ttl': None,
                'type': 'TXT',
                'value': txt_match.group(1),
            })

    # Fallback to Python resolution
    if not records and record_type in ('A', 'AAAA'):
        records = _python_resolve(domain, record_type)

    return {
        'domain': domain,
        'record_type': record_type,
        'dns_server': server_used,
        'records': records,
        'query_time': None,
        'authoritative': authoritative,
        'error': None if records else 'No se encontraron registros',
    }


def _python_resolve(domain: str, record_type: str = "A") -> list:
    """Last-resort Python socket resolution for A/AAAA records."""
    records = []
    try:
        if record_type == 'AAAA':
            family = socket.AF_INET6
        else:
            family = socket.AF_INET

        results = socket.getaddrinfo(domain, None, family, socket.SOCK_STREAM)
        seen = set()
        for res in results:
            ip = res[4][0]
            if ip not in seen:
                seen.add(ip)
                records.append({
                    'name': domain,
                    'ttl': None,
                    'type': record_type,
                    'value': ip,
                })
    except socket.gaierror:
        pass

    return records


def reverse_lookup(ip: str) -> dict:
    """Perform reverse DNS lookup for an IP address."""
    try:
        ip = ip.strip()
        if not re.match(r'^[\d\.:a-fA-F]+$', ip):
            raise ValueError(f"IP no válida: {ip}")

        hostname, _, _ = socket.gethostbyaddr(ip)
        return {
            'ip': ip,
            'hostname': hostname,
            'error': None,
        }
    except socket.herror:
        return {
            'ip': ip,
            'hostname': None,
            'error': 'No se encontró registro PTR',
        }
    except Exception as e:
        return {
            'ip': ip,
            'hostname': None,
            'error': str(e),
        }
