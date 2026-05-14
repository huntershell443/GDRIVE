import sys
import asyncio
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
import os
import platform
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


@database_sync_to_async
def _user_owns_project(user, project_id):
    if not user or not getattr(user, 'is_authenticated', False):
        return False
    try:
        from file_manager.models import Project
        return Project.objects.filter(pk=project_id, user=user).exists()
    except Exception:
        return False


class TerminalConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user', None)
        project_id = self.scope['url_route']['kwargs'].get('project_id')

        if not user or not getattr(user, 'is_authenticated', False):
            await self.close(code=4401)
            return

        if not await _user_owns_project(user, project_id):
            await self.close(code=4403)
            return

        await self.accept()
        self.process = None
        self.os_type = platform.system().lower()
        if self.os_type == 'windows':
            self.shell = 'cmd.exe'
            self.args = ['/K']
        else:
            self.shell = '/bin/bash'
            self.args = []
        self.process = await asyncio.create_subprocess_exec(
            self.shell, *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT
        )
        self.reading = True
        asyncio.create_task(self.read_output())

    async def disconnect(self, close_code):
        self.reading = False
        if getattr(self, 'process', None):
            try:
                self.process.terminate()
                await self.process.wait()
            except Exception:
                pass

    async def receive(self, text_data=None, bytes_data=None):
        if getattr(self, 'process', None) and text_data:
            try:
                if self.os_type == 'windows':
                    text_data = text_data.replace('\r', '\r\n')
                self.process.stdin.write(text_data.encode())
                await self.process.stdin.drain()
            except Exception:
                pass

    async def read_output(self):
        try:
            while self.reading and self.process:
                data = await self.process.stdout.read(1024)
                if not data:
                    await asyncio.sleep(0.05)
                    continue
                await self.send(data.decode(errors='ignore'))
        except Exception:
            pass
