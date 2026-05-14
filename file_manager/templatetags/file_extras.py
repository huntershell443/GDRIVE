from django import template
import os

register = template.Library()

@register.filter
def extension(value):
    return os.path.splitext(value.name)[1][1:].lower()

@register.filter
def icon_for_file(file):
    ext = os.path.splitext(file.name)[1][1:].lower()
    icon_map = {
        'pdf': '📕',
        'doc': '📄',
        'docx': '📄',
        'txt': '📝',
        'xls': '📊',
        'xlsx': '📊',
        'zip': '📦',
        'rar': '📦',
        '7z': '📦',
        'tar': '📦',
        'mp3': '🎵',
        'wav': '🎵',
        'ogg': '🎵',
        'mp4': '🎥',
        'avi': '🎥',
        'mkv': '🎥',
        'mov': '🎥',
        'jpg': '🖼️',
        'jpeg': '🖼️',
        'png': '🖼️',
        'gif': '🖼️',
        'bmp': '🖼️',
        'svg': '🖼️',
        'py': '🐍',
        'js': '📜',
        'html': '🌐',
        'css': '🎨',
        'json': '📋',
        'xml': '📋',
        'exe': '⚙️',
        'deb': '📦',
        'iso': '💿',
    }
    return icon_map.get(ext, '📄')  # Retorna emoji baseado na extensão