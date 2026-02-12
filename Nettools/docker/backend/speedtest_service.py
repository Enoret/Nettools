"""
NetTools - Speed Test Service
Uses official Ookla Speedtest CLI with fallback to Python speedtest-cli
"""

import subprocess
import json
import logging
import shutil

logger = logging.getLogger(__name__)


def _has_official_speedtest() -> bool:
    """
    Check if official Ookla speedtest CLI is available.
    Must distinguish from Python speedtest-cli which may also be aliased as 'speedtest'.
    The official Ookla CLI outputs 'Speedtest by Ookla' in --version.
    The Python version outputs 'speedtest-cli X.X.X'.
    """
    binary = shutil.which('speedtest')
    if not binary:
        return False

    try:
        result = subprocess.run(
            ['speedtest', '--version'],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = (result.stdout + result.stderr).lower()
        # Official Ookla CLI contains "speedtest by ookla" or "ookla"
        if 'ookla' in output:
            logger.info("Detected official Ookla Speedtest CLI")
            return True
        # Python speedtest-cli contains "speedtest-cli" and "python"
        if 'speedtest-cli' in output or 'python' in output:
            logger.info("Detected Python speedtest-cli (not official Ookla), will use fallback mode")
            return False
        # Unknown binary — try it anyway
        logger.info(f"Unknown speedtest binary detected, assuming official: {output[:100]}")
        return True
    except Exception as e:
        logger.warning(f"Could not check speedtest version: {e}")
        return False


def get_servers() -> list:
    """
    Get a list of available speedtest servers.
    Returns a list of server dicts with id, sponsor (or name), name (city), country, d (distance).
    Tries official Ookla CLI first, falls back to Python speedtest-cli.
    """
    try:
        logger.info("Fetching speedtest server list...")

        # Try official Ookla CLI first
        if _has_official_speedtest():
            return _get_servers_official()
        else:
            return _get_servers_fallback()

    except Exception as e:
        logger.error(f"Error fetching servers: {e}")
        # Try fallback if primary fails
        try:
            return _get_servers_fallback()
        except Exception as e2:
            logger.error(f"Fallback server list also failed: {e2}")
            return []


def _get_servers_official() -> list:
    """Get servers using official Ookla Speedtest CLI."""
    try:
        logger.info("Using official Ookla Speedtest CLI for server list...")

        result = subprocess.run(
            ['speedtest', '--servers', '--format=json', '--accept-license', '--accept-gdpr'],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            logger.error(f"Official speedtest --servers error: {result.stderr}")
            raise Exception(f"speedtest --servers failed: {result.stderr}")

        data = json.loads(result.stdout)
        servers = []

        # Parse the servers array from official CLI response
        if 'servers' in data:
            for server in data['servers']:
                servers.append({
                    'id': str(server.get('id', '')),
                    'sponsor': server.get('sponsor', server.get('name', 'Unknown')),
                    'name': server.get('location', server.get('name', '')),
                    'country': server.get('country', ''),
                    'd': server.get('distance'),
                })

        # Sort by distance (closest first), limit to top 30
        servers.sort(key=lambda s: s.get('d') or 99999)
        logger.info(f"Found {len(servers)} speedtest servers (official CLI)")
        return servers[:30]

    except subprocess.TimeoutExpired:
        logger.error("Official server list fetch timed out")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse official speedtest output: {e}")
        raise
    except FileNotFoundError:
        logger.error("Official speedtest not found")
        raise


def _get_servers_fallback() -> list:
    """Get servers using Python speedtest-cli as fallback."""
    try:
        cli_cmd = _get_speedtest_cli_cmd()
        logger.info(f"Using {cli_cmd} (Python) for server list...")

        result = subprocess.run(
            [cli_cmd, '--list'],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            logger.error(f"speedtest-cli --list error: {result.stderr}")
            raise Exception(f"speedtest-cli --list failed: {result.stderr}")

        servers = []
        for line in result.stdout.strip().split('\n'):
            line = line.strip()
            if not line or line.startswith('Retrieving') or line.startswith('='):
                continue
            # Format: "ID) Sponsor (City, Country) [Distance km]"
            try:
                # Split ID from the rest
                id_part, rest = line.split(')', 1)
                server_id = id_part.strip()

                # Extract distance from brackets
                distance = None
                if '[' in rest and ']' in rest:
                    dist_str = rest[rest.rfind('[') + 1:rest.rfind(']')]
                    dist_str = dist_str.replace('km', '').strip()
                    try:
                        distance = float(dist_str)
                    except ValueError:
                        pass
                    rest = rest[:rest.rfind('[')].strip()

                # Extract location from parentheses
                name = ''
                country = ''
                if '(' in rest and ')' in rest:
                    loc_str = rest[rest.rfind('(') + 1:rest.rfind(')')]
                    parts = loc_str.split(',')
                    if len(parts) >= 2:
                        name = parts[0].strip()
                        country = ','.join(parts[1:]).strip()
                    else:
                        name = loc_str.strip()
                    sponsor = rest[:rest.rfind('(')].strip()
                else:
                    sponsor = rest.strip()

                servers.append({
                    'id': server_id,
                    'sponsor': sponsor,
                    'name': name,
                    'country': country,
                    'd': distance,
                })
            except Exception:
                continue

        # Sort by distance (closest first), limit to top 30
        servers.sort(key=lambda s: s.get('d') or 99999)
        logger.info(f"Found {len(servers)} speedtest servers (speedtest-cli)")
        return servers[:30]

    except subprocess.TimeoutExpired:
        logger.error("Server list fetch timed out")
        raise
    except FileNotFoundError:
        logger.error("speedtest-cli not found")
        raise


def run_speed_test(server_id: str = None) -> dict:
    """
    Run a speed test using official Ookla Speedtest CLI with fallback to Python speedtest-cli.
    Optionally specify a server_id to test against a specific server.
    Returns parsed results with keys:
    - download_speed (Mbps)
    - upload_speed (Mbps)
    - ping
    - jitter
    - server_name
    - server_id
    - server_location
    - isp
    - external_ip
    - raw_data
    """
    try:
        logger.info(f"Starting speed test...{' (server: ' + server_id + ')' if server_id else ''}")

        # Try official Ookla CLI first
        if _has_official_speedtest():
            return _run_speed_test_official(server_id)
        else:
            return _run_speed_test_fallback(server_id)

    except Exception as e:
        logger.error(f"Speed test error: {e}")
        # Try fallback if primary fails
        try:
            return _run_speed_test_fallback(server_id)
        except Exception as e2:
            logger.error(f"Fallback speed test also failed: {e2}")
            raise


def _run_speed_test_official(server_id: str = None) -> dict:
    """Run speed test using official Ookla Speedtest CLI."""
    try:
        logger.info("Using official Ookla Speedtest CLI...")

        cmd = ['speedtest', '--format=json', '--accept-license', '--accept-gdpr']
        if server_id:
            cmd.extend(['--server-id', str(server_id)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            logger.error(f"Official speedtest error: {result.stderr}")
            raise Exception(f"Official speedtest failed: {result.stderr}")

        raw = json.loads(result.stdout)

        # Convert bytes/sec to Mbps (multiply by 8 / 1_000_000)
        download_bandwidth = raw.get('download', {}).get('bandwidth', 0)
        upload_bandwidth = raw.get('upload', {}).get('bandwidth', 0)

        download_mbps = round(download_bandwidth * 8 / 1_000_000, 2)
        upload_mbps = round(upload_bandwidth * 8 / 1_000_000, 2)

        parsed = {
            'download_speed': download_mbps,
            'upload_speed': upload_mbps,
            'ping': round(raw.get('ping', {}).get('latency', 0), 2),
            'jitter': round(raw.get('ping', {}).get('jitter', 0), 2),
            'server_name': raw.get('server', {}).get('name', 'Unknown'),
            'server_id': str(raw.get('server', {}).get('id', '')),
            'server_location': f"{raw.get('server', {}).get('name', '')}, {raw.get('server', {}).get('country', '')}",
            'isp': raw.get('isp', 'Unknown'),
            'external_ip': raw.get('interface', {}).get('externalIp', ''),
            'raw_data': raw,
        }

        logger.info(f"Speed test completed (official): DL={parsed['download_speed']}Mbps UL={parsed['upload_speed']}Mbps Ping={parsed['ping']}ms")
        return parsed

    except subprocess.TimeoutExpired:
        logger.error("Official speed test timed out")
        raise Exception("El test de velocidad ha expirado (timeout)")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse official speedtest output: {e}")
        raise Exception("Error al procesar los resultados del test")
    except FileNotFoundError:
        logger.error("Official speedtest not found")
        raise


def _get_speedtest_cli_cmd() -> str:
    """Find the correct command for Python speedtest-cli."""
    # Try speedtest-cli first (most explicit)
    if shutil.which('speedtest-cli'):
        return 'speedtest-cli'
    # On some systems, the Python version is installed as 'speedtest'
    if shutil.which('speedtest'):
        return 'speedtest'
    return 'speedtest-cli'  # default, let it fail with FileNotFoundError


def _run_speed_test_fallback(server_id: str = None) -> dict:
    """Run speed test using Python speedtest-cli as fallback."""
    try:
        cli_cmd = _get_speedtest_cli_cmd()
        logger.info(f"Using {cli_cmd} (Python) as fallback...")

        cmd = [cli_cmd, '--json']
        if server_id:
            cmd.extend(['--server', str(server_id)])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            logger.error(f"speedtest-cli error: {result.stderr}")
            raise Exception(f"speedtest-cli failed: {result.stderr}")

        raw = json.loads(result.stdout)

        # speedtest-cli returns bits/s, convert to Mbps
        parsed = {
            'download_speed': round(raw.get('download', 0) / 1_000_000, 2),
            'upload_speed': round(raw.get('upload', 0) / 1_000_000, 2),
            'ping': round(raw.get('ping', 0), 2),
            'jitter': round(raw.get('server', {}).get('latency', 0), 2),
            'server_name': raw.get('server', {}).get('sponsor', 'Unknown'),
            'server_id': str(raw.get('server', {}).get('id', '')),
            'server_location': f"{raw.get('server', {}).get('name', '')}, {raw.get('server', {}).get('country', '')}",
            'isp': raw.get('client', {}).get('isp', 'Unknown'),
            'external_ip': raw.get('client', {}).get('ip', ''),
            'raw_data': raw,
        }

        logger.info(f"Speed test completed (speedtest-cli): DL={parsed['download_speed']}Mbps UL={parsed['upload_speed']}Mbps Ping={parsed['ping']}ms")
        return parsed

    except subprocess.TimeoutExpired:
        logger.error("Speed test timed out")
        raise Exception("El test de velocidad ha expirado (timeout)")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse speedtest-cli output: {e}")
        raise Exception("Error al procesar los resultados del test")
    except FileNotFoundError:
        logger.error("speedtest-cli not found")
        raise Exception("speedtest-cli no esta instalado")
    except Exception as e:
        logger.error(f"Fallback speed test error: {e}")
        raise
