"""One-command local sandbox launcher. Uses Compose; preserves configuration and data."""
import argparse
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent.parent


def read_config():
    result = {}
    path = ROOT / '.env'
    if path.exists():
        for line in path.read_text().splitlines():
            if line.strip() and not line.lstrip().startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                result[key.strip()] = value.strip().strip('\"\'')
    return result


def main():
    parser = argparse.ArgumentParser(description='AgentPass: frontend, FastAPI, PostgreSQL, webhook worker')
    parser.add_argument('action', choices=['start', 'stop', 'status'], nargs='?', default='start')
    parser.add_argument('--port', type=int, help='Frontend port (default: WEB_PORT or 3000)')
    parser.add_argument('--bind', help='Frontend bind address; managed workspace default is 0.0.0.0')
    parser.add_argument('--origin', help='Exact browser origin for an external port preview or reverse proxy')
    parser.add_argument('--no-build', action='store_true', help='Reuse already built images')
    args = parser.parse_args()
    managed = os.environ.get('AGENTPASS_CLOUD', '').lower() in {'1', 'true', 'yes'}
    env = os.environ.copy()
    if managed:
        for key in ('DOCKER_HOST', 'DOCKER_CONTEXT', 'DOCKER_TLS', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH'):
            env.pop(key, None)
    docker = ['docker'] + (['--host=unix:///var/run/docker.sock'] if managed else [])
    try:
        subprocess.run(docker + ['info', '--format', '{{.ServerVersion}}'], env=env, check=True, stdout=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError):
        raise SystemExit('Docker недоступен. Запустите Docker с Compose v2 и повторите команду.')
    subprocess.run([sys.executable, str(ROOT / 'infra/bootstrap.py')], cwd=ROOT, check=True)
    config = read_config()
    port = args.port or int(env.get('WEB_PORT', config.get('WEB_PORT', '3000')))
    if not 1 <= port <= 65535:
        parser.error('Порт должен быть от 1 до 65535')
    origin = args.origin or env.get('WEB_ORIGIN', config.get('WEB_ORIGIN', f'http://localhost:{port}'))
    if not args.origin and origin == 'http://localhost:3000' and port != 3000:
        origin = f'http://localhost:{port}'
    parsed = urlsplit(origin)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.path not in ('', '/') or parsed.query or parsed.fragment or parsed.username:
        parser.error('--origin должен содержать только http(s)://host[:port]')
    env['WEB_PORT'] = str(port)
    env['WEB_BIND_ADDRESS'] = args.bind or env.get('WEB_BIND_ADDRESS', config.get('WEB_BIND_ADDRESS', '0.0.0.0' if managed else '127.0.0.1'))
    env['WEB_ORIGIN'] = origin.rstrip('/')
    compose = docker + ['compose', '--env-file', str(ROOT / '.env'), '-f', str(ROOT / 'infra/compose.yml')]
    if managed:
        compose += ['-f', str(ROOT / 'infra/compose.cloud.yml')]
    if args.action == 'stop':
        subprocess.run(compose + ['stop'], cwd=ROOT, env=env, check=True)
        print('AgentPass остановлен. База данных и конфигурация сохранены.')
        return
    if args.action == 'status':
        subprocess.run(compose + ['ps'], cwd=ROOT, env=env, check=True)
        return
    if managed and not args.no_build and shutil.disk_usage(ROOT).free < 10 * 1024**3:
        print('Освобождаю неиспользуемый кэш Docker перед сборкой; данные и образы сохраняются.', flush=True)
        subprocess.run(docker + ['builder', 'prune', '--all', '--force'], env=env, check=True)
    command = compose + ['up', '-d', '--wait', '--wait-timeout', '120']
    if not args.no_build:
        command.append('--build')
    subprocess.run(command, cwd=ROOT, env=env, check=True)
    endpoint = f'http://127.0.0.1:{port}/login'
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        try:
            with urlopen(endpoint, timeout=2) as response:
                if response.status == 200:
                    break
        except OSError:
            pass
        time.sleep(0.5)
    else:
        raise SystemExit('Frontend не ответил. Проверьте npm run sandbox:status и Docker logs.')
    print(f'\nAgentPass готов: {origin.rstrip("/")}\n')
    print('Откройте страницу входа и нажмите «Открыть полный sandbox».')
    print('Доступны Dashboard, Developer Portal, Agent Console и Admin Console.')
    print(f'OpenAPI через frontend: {origin.rstrip("/")}/api/v1/docs')
    print('Для предпросмотра удалённого терминала откройте порт', port)
    print('Если у предпросмотра другой origin: npm run sandbox -- --origin https://<preview-host> --no-build')
    print('Остановка: npm run sandbox:stop. Данные сохраняются между запусками.')


if __name__ == '__main__':
    try:
        main()
    except subprocess.CalledProcessError as error:
        raise SystemExit(error.returncode)
