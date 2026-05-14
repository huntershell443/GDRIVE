from django.contrib import admin
from django.utils.html import format_html, mark_safe
from django.db.models import Q
from django.contrib import messages
from django.conf import settings
from django.http import JsonResponse
from django.urls import path
from django import forms
import os, re, sys
from .models import (
    File, UserStorage, Note, Dork, CVE, Tool, Project,
    Folder, DorkNote, ToolNote, ProjectItem, YouTubeChannel,
    ResourceLink, GlobalFile, SharedResource, SystemConfig
)

# Ações personalizadas para compartilhamento global
def make_global(modeladmin, request, queryset):
    updated = queryset.update(is_global=True, global_created_by=request.user)
    modeladmin.message_user(request, f"✅ {updated} itens marcados como GLOBAIS (compartilhados com todos os usuários).")
make_global.short_description = "📢 Tornar selecionados GLOBAIS"

def remove_global(modeladmin, request, queryset):
    updated = queryset.update(is_global=False, global_created_by=None)
    modeladmin.message_user(request, f"🚫 {updated} itens removidos do compartilhamento global.")
remove_global.short_description = "🚫 Remover selecionados do compartilhamento global"

def duplicate_to_all_users(modeladmin, request, queryset):
    from django.contrib.auth.models import User
    users = User.objects.exclude(id=request.user.id)
    created_count = 0
    
    for item in queryset:
        for user in users:
            if isinstance(item, CVE):
                CVE.objects.create(
                    cve_id=item.cve_id,
                    description=item.description,
                    severity=item.severity,
                    references=item.references,
                    published_date=item.published_date,
                    user=user
                )
            elif isinstance(item, Dork):
                Dork.objects.create(
                    query=item.query,
                    description=item.description,
                    platform=item.platform,
                    user=user
                )
            elif isinstance(item, Tool):
                Tool.objects.create(
                    name=item.name,
                    category=item.category,
                    description=item.description,
                    homepage=item.homepage,
                    user=user
                )
            elif isinstance(item, ResourceLink):
                ResourceLink.objects.create(
                    title=item.title,
                    url=item.url,
                    description=item.description,
                    user=user
                )
            elif isinstance(item, YouTubeChannel):
                YouTubeChannel.objects.create(
                    name=item.name,
                    url=item.url,
                    description=item.description,
                    user=user
                )
            elif isinstance(item, Note):
                Note.objects.create(
                    title=item.title,
                    content=item.content,
                    tags=item.tags,
                    user=user,
                    folder=item.folder
                )
            elif isinstance(item, File):
                File.objects.create(
                    name=item.name,
                    file=item.file,
                    folder=item.folder,
                    user=user,
                    thumbnail=item.thumbnail
                )
            created_count += 1
    
    modeladmin.message_user(request, f"👥 {created_count} cópias criadas para todos os usuários.")
duplicate_to_all_users.short_description = "👥 Duplicar para TODOS os usuários"

class CVEYearFilter(admin.SimpleListFilter):
    title = 'Ano da CVE'
    parameter_name = 'cve_year'

    def lookups(self, request, model_admin):
        years = (
            model_admin.model.objects
            .values_list('cve_id', flat=True)
        )
        year_set = set()
        for cve in years:
            if cve and cve.startswith('CVE-'):
                parts = cve.split('-')
                if len(parts) >= 3 and parts[1].isdigit():
                    year_set.add(parts[1])
        return sorted([(year, year) for year in year_set], reverse=True)

    def queryset(self, request, queryset):
        year = self.value()
        if year:
            return queryset.filter(cve_id__startswith=f'CVE-{year}-')
        return queryset

@admin.register(CVE)
class CVEAdmin(admin.ModelAdmin):
    list_display = ('cve_id', 'severity_colored', 'published_date', 'user', 'is_global_display', 'reference_link')
    search_fields = ('cve_id', 'description', 'severity')
    list_filter = ('severity', 'user', 'is_global', CVEYearFilter, 'published_date')
    ordering = ('-published_date',)
    actions = [make_global, remove_global, duplicate_to_all_users]

    def is_global_display(self, obj):
        if obj.is_global:
            return format_html('✅ <span style="color: green; font-weight: bold;">GLOBAL</span>')
        return format_html('👤 <span style="color: blue;">Privado</span>')
    is_global_display.short_description = 'Status'

    def severity_colored(self, obj):
        color_map = {
            'Critical': 'red',
            'High': 'darkorange',
            'Medium': 'goldenrod',
            'Low': 'green',
        }
        color = color_map.get((obj.severity or '').capitalize(), 'gray')
        return format_html('<b style="color: {};">{}</b>', color, obj.severity or 'N/A')
    severity_colored.short_description = 'Severity'

    def reference_link(self, obj):
        if obj.references:
            return format_html('<a href="{}" target="_blank">🔗 Referência</a>', obj.references)
        return '-'
    reference_link.short_description = 'Referência'

@admin.register(Tool)
class ToolAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'user', 'is_global_display', 'homepage_link', 'created_at')
    search_fields = ('name', 'category', 'description')
    list_filter = ('category', 'created_at', 'is_global')
    ordering = ('-created_at',)
    actions = [make_global, remove_global, duplicate_to_all_users]

    def is_global_display(self, obj):
        if obj.is_global:
            return format_html('✅ <span style="color: green; font-weight: bold;">GLOBAL</span>')
        return format_html('👤 <span style="color: blue;">Privado</span>')
    is_global_display.short_description = 'Status'

    def homepage_link(self, obj):
        if obj.homepage:
            return format_html('<a href="{}" target="_blank">🌐 Site</a>', obj.homepage)
        return '-'
    homepage_link.short_description = 'Homepage'

@admin.register(Dork)
class DorkAdmin(admin.ModelAdmin):
    list_display = ('query_short', 'platform', 'user', 'is_global_display', 'created_at')
    search_fields = ('query', 'description', 'platform')
    list_filter = ('platform', 'is_global', 'created_at')
    ordering = ('-created_at',)
    actions = [make_global, remove_global, duplicate_to_all_users]

    def query_short(self, obj):
        return obj.query[:60] + '...' if len(obj.query) > 60 else obj.query
    query_short.short_description = 'Query'

    def is_global_display(self, obj):
        if obj.is_global:
            return format_html('✅ <span style="color: green; font-weight: bold;">GLOBAL</span>')
        return format_html('👤 <span style="color: blue;">Privado</span>')
    is_global_display.short_description = 'Status'

@admin.register(ResourceLink)
class ResourceLinkAdmin(admin.ModelAdmin):
    list_display = ('title', 'url_display', 'user', 'is_global_display', 'created_at')
    search_fields = ('title', 'description', 'url')
    list_filter = ('is_global', 'created_at')
    actions = [make_global, remove_global, duplicate_to_all_users]

    def is_global_display(self, obj):
        if obj.is_global:
            return format_html('✅ <span style="color: green; font-weight: bold;">GLOBAL</span>')
        return format_html('👤 <span style="color: blue;">Privado</span>')
    is_global_display.short_description = 'Status'

    def url_display(self, obj):
        return format_html('<a href="{}" target="_blank">🔗 {}</a>', obj.url, obj.url[:50] + '...' if len(obj.url) > 50 else obj.url)
    url_display.short_description = 'URL'

@admin.register(YouTubeChannel)
class YouTubeChannelAdmin(admin.ModelAdmin):
    list_display = ('name', 'url_link', 'user', 'is_global_display', 'description_short')
    search_fields = ('name', 'url', 'description')
    list_filter = ('is_global',)
    actions = [make_global, remove_global, duplicate_to_all_users]

    def is_global_display(self, obj):
        if obj.is_global:
            return format_html('✅ <span style="color: green; font-weight: bold;">GLOBAL</span>')
        return format_html('👤 <span style="color: blue;">Privado</span>')
    is_global_display.short_description = 'Status'

    def url_link(self, obj):
        return format_html('<a href="{}" target="_blank">🎥 {}</a>', obj.url, obj.url)
    url_link.short_description = 'URL'

    def description_short(self, obj):
        return obj.description[:80] + '...' if len(obj.description) > 80 else obj.description
    description_short.short_description = 'Descrição'

@admin.register(GlobalFile)
class GlobalFileAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'uploaded_by', 'uploaded_at', 'file_link')
    search_fields = ('name', 'description', 'category')
    list_filter = ('category', 'uploaded_at')
    ordering = ('-uploaded_at',)

    def file_link(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">📥 Download</a>', obj.file.url)
        return '-'
    file_link.short_description = 'Arquivo'

@admin.register(File)
class FileAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'is_global_display', 'uploaded_at', 'file_link')
    list_filter = ('user', 'uploaded_at', 'is_global')
    search_fields = ('name',)
    ordering = ('-uploaded_at',)
    actions = [make_global, remove_global, duplicate_to_all_users]

    def is_global_display(self, obj):
        if obj.is_global:
            return format_html('✅ <span style="color: green; font-weight: bold;">GLOBAL</span>')
        return format_html('👤 <span style="color: blue;">Privado</span>')
    is_global_display.short_description = 'Status'

    def file_link(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank" class="btn btn-sm btn-outline-primary">📥</a>', obj.file.url)
        return '-'
    file_link.short_description = 'Download'

@admin.register(UserStorage)
class UserStorageAdmin(admin.ModelAdmin):
    list_display = ('user', 'plan', 'custom_limit_gb', 'get_limit_display')
    list_editable = ('plan', 'custom_limit_gb')
    search_fields = ('user__username',)

    def get_limit_display(self, obj):
        return f"{obj.get_storage_limit_bytes() / 1024**3:.2f} GB"
    get_limit_display.short_description = 'Limite Efetivo'

@admin.register(Note)
class NoteAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'is_global_display', 'created_at', 'tags_short')
    search_fields = ('title', 'content', 'tags')
    list_filter = ('user', 'created_at', 'is_global')
    actions = [make_global, remove_global, duplicate_to_all_users]

    def is_global_display(self, obj):
        if obj.is_global:
            return format_html('✅ <span style="color: green; font-weight: bold;">GLOBAL</span>')
        return format_html('👤 <span style="color: blue;">Privado</span>')
    is_global_display.short_description = 'Status'

    def tags_short(self, obj):
        return obj.tags[:50] + '...' if len(obj.tags) > 50 else obj.tags
    tags_short.short_description = 'Tags'

@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'parent_info', 'items_count')
    search_fields = ('name',)
    list_filter = ('user',)

    def parent_info(self, obj):
        if obj.parent:
            return format_html('<span style="color: gray;">↳ {}</span>', obj.parent.name)
        return '-'
    parent_info.short_description = 'Pasta Pai'

    def items_count(self, obj):
        count = obj.projectitem_set.count()
        return format_html('<span class="badge bg-info">{}</span>', count)
    items_count.short_description = 'Itens'

@admin.register(ProjectItem)
class ProjectItemAdmin(admin.ModelAdmin):
    list_display = ('title', 'project', 'file_display', 'link_display', 'notes_short')
    search_fields = ('title', 'notes', 'project__name')
    list_filter = ('project',)

    def file_display(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">📎 Arquivo</a>', obj.file.url)
        return '-'
    file_display.short_description = 'Arquivo'

    def link_display(self, obj):
        if obj.link:
            return format_html('<a href="{}" target="_blank">🔗 Link</a>', obj.link)
        return '-'
    link_display.short_description = 'Link'

    def notes_short(self, obj):
        return obj.notes[:80] + '...' if obj.notes and len(obj.notes) > 80 else obj.notes
    notes_short.short_description = 'Notas'

@admin.register(SharedResource)
class SharedResourceAdmin(admin.ModelAdmin):
    list_display = ('resource_type', 'resource_id', 'shared_by', 'shared_with_all_display', 'permission', 'created_at')
    list_filter = ('resource_type', 'shared_with_all', 'permission', 'created_at')
    search_fields = ('shared_by__username', 'resource_type')
    readonly_fields = ('created_at',)

    def shared_with_all_display(self, obj):
        if obj.shared_with_all:
            return format_html('✅ <span style="color: green; font-weight: bold;">TODOS</span>')
        else:
            users_count = obj.shared_with.count()
            return format_html('👥 <span style="color: blue;">{} usuário(s)</span>', users_count)
    shared_with_all_display.short_description = 'Compartilhado com'

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related('shared_with')

@admin.register(Folder)
class FolderAdmin(admin.ModelAdmin):
    list_display = ('name', 'user', 'parent_info', 'created_at', 'subfolders_count')
    list_filter = ('user', 'created_at')
    search_fields = ('name', 'user__username')

    def parent_info(self, obj):
        if obj.parent:
            return format_html('<span style="color: gray;">↳ {}</span>', obj.parent.name)
        return format_html('<span style="color: green; font-weight: bold;">📁 Raiz</span>')
    parent_info.short_description = 'Pasta Pai'

    def subfolders_count(self, obj):
        count = obj.subfolders.count()
        return format_html('<span class="badge bg-secondary">{}</span>', count)
    subfolders_count.short_description = 'Subpastas'

@admin.register(DorkNote)
class DorkNoteAdmin(admin.ModelAdmin):
    list_display = ('dork', 'user', 'note_short', 'created_at')
    list_filter = ('user', 'created_at')
    search_fields = ('note', 'dork__query')

    def note_short(self, obj):
        return obj.note[:100] + '...' if len(obj.note) > 100 else obj.note
    note_short.short_description = 'Nota'

@admin.register(ToolNote)
class ToolNoteAdmin(admin.ModelAdmin):
    list_display = ('tool', 'user', 'note_short', 'created_at')
    list_filter = ('user', 'created_at')
    search_fields = ('note', 'tool__name')

    def note_short(self, obj):
        return obj.note[:100] + '...' if len(obj.note) > 100 else obj.note
    note_short.short_description = 'Nota'

class DirectoryPickerWidget(forms.TextInput):
    """Campo de texto + botão que abre explorador de diretórios do servidor."""

    def render(self, name, value, attrs=None, renderer=None):
        attrs = attrs or {}
        field_id = f'id_{name}'
        attrs.update({'style': 'width:420px;font-family:monospace;', 'id': field_id})
        text_html = super().render(name, value, attrs, renderer)
        default_root = 'C:\\\\' if sys.platform == 'win32' else '/'

        html = text_html
        html += f'''
        <button type="button"
                onclick="dirBrowserOpen('{field_id}')"
                style="margin-left:8px;padding:6px 14px;cursor:pointer;
                       background:#417690;color:#fff;border:none;border-radius:4px;
                       font-size:13px;vertical-align:middle;">
            &#128193; Navegar
        </button>
        <p class="help" style="margin-top:4px;">
            Clique em <strong>&#128193; Navegar</strong> para escolher o diretório no servidor,
            ou digite o caminho diretamente.
        </p>

        <div id="dir-browser-modal"
             style="display:none;position:fixed;inset:0;z-index:99999;
                    background:rgba(0,0,0,.80);backdrop-filter:blur(6px);
                    align-items:center;justify-content:center;">

            <div style="background:#0f1117;border:1px solid #00ffc8;border-radius:14px;
                        width:min(860px,96vw);height:min(640px,88vh);
                        display:flex;flex-direction:column;
                        box-shadow:0 0 60px rgba(0,255,200,.18),0 12px 48px rgba(0,0,0,.8);">

                <!-- Header -->
                <div style="display:flex;align-items:center;justify-content:space-between;
                            padding:16px 22px;border-bottom:1px solid rgba(0,255,200,.2);
                            flex-shrink:0;">
                    <span style="color:#00ffc8;font-size:15px;font-weight:700;
                                 text-shadow:0 0 10px rgba(0,255,200,.4);">
                        &#128193; Selecionar Diretório de Armazenamento
                    </span>
                    <button type="button" onclick="dirBrowserClose()"
                            style="background:rgba(255,68,68,.15);border:1px solid rgba(255,68,68,.5);
                                   color:#ff4444;border-radius:7px;width:32px;height:32px;
                                   cursor:pointer;font-size:14px;display:flex;align-items:center;
                                   justify-content:center;flex-shrink:0;">&#10005;</button>
                </div>

                <!-- Barra de caminho atual -->
                <div style="padding:10px 22px;background:rgba(0,255,200,.05);
                            border-bottom:1px solid rgba(0,255,200,.12);
                            display:flex;align-items:center;gap:10px;flex-shrink:0;">
                    <span style="color:#888;font-size:11px;white-space:nowrap;
                                 text-transform:uppercase;letter-spacing:.5px;">Caminho:</span>
                    <code id="dir-current-path"
                          style="color:#00ffc8;font-size:13px;word-break:break-all;
                                 flex:1;font-family:monospace;"></code>
                    <button type="button" onclick="dirBrowserSelect()"
                            style="background:rgba(0,255,200,.15);border:1px solid rgba(0,255,200,.4);
                                   color:#00ffc8;border-radius:6px;padding:5px 12px;
                                   cursor:pointer;font-size:12px;white-space:nowrap;font-weight:600;
                                   flex-shrink:0;">
                        &#10003; Usar este
                    </button>
                </div>

                <!-- Lista de pastas -->
                <div id="dir-list"
                     style="flex:1;overflow-y:auto;padding:8px 12px;
                            scrollbar-width:thin;scrollbar-color:#00ffc8 #1a1a2e;">
                    <div style="color:#888;padding:30px;text-align:center;">Carregando&#8230;</div>
                </div>

                <!-- Footer com botão principal -->
                <div style="padding:14px 22px;border-top:1px solid rgba(0,255,200,.15);
                            display:flex;align-items:center;justify-content:space-between;
                            flex-shrink:0;gap:12px;flex-wrap:wrap;">
                    <span style="color:#666;font-size:12px;">
                        Clique em uma pasta para navegar &bull; depois confirme abaixo
                    </span>
                    <div style="display:flex;gap:10px;">
                        <button type="button" onclick="dirBrowserClose()"
                                style="padding:9px 20px;background:transparent;
                                       color:#aaa;border:1px solid #333;
                                       border-radius:8px;cursor:pointer;font-size:13px;">
                            Cancelar
                        </button>
                        <button type="button" onclick="dirBrowserSelect()"
                                style="padding:9px 24px;
                                       background:linear-gradient(135deg,#00ffc8,#b967ff);
                                       color:#000;border:none;border-radius:8px;
                                       cursor:pointer;font-weight:700;font-size:13px;
                                       box-shadow:0 0 16px rgba(0,255,200,.3);">
                            &#10003; Confirmar Diretório
                        </button>
                    </div>
                </div>
            </div>
        </div>

        <script>
        (function() {{
            var _fieldId = null;

            window.dirBrowserOpen = function(fieldId) {{
                _fieldId = fieldId;
                var current = document.getElementById(fieldId).value || '';
                // Move para o body na primeira chamada para escapar de qualquer overflow/transform do admin
                var modal = document.getElementById('dir-browser-modal');
                if (modal.parentElement !== document.body) {{
                    document.body.appendChild(modal);
                }}
                modal.style.display = 'flex';
                dirBrowserLoad(current || '{default_root}');
            }};

            window.dirBrowserClose = function() {{
                document.getElementById('dir-browser-modal').style.display = 'none';
            }};

            window.dirBrowserSelect = function() {{
                var p = document.getElementById('dir-current-path').textContent;
                if (_fieldId && p) {{
                    document.getElementById(_fieldId).value = p;
                }}
                dirBrowserClose();
            }};

            window.dirBrowserLoad = function(path) {{
                document.getElementById('dir-list').innerHTML =
                    '<div style="color:#888;padding:30px;text-align:center;">Carregando&#8230;</div>';
                document.getElementById('dir-current-path').textContent = path;

                fetch('/admin/file_manager/systemconfig/browse-dir/?path=' + encodeURIComponent(path))
                    .then(function(r) {{ return r.json(); }})
                    .then(function(data) {{
                        document.getElementById('dir-current-path').textContent = data.current;
                        var html = '';

                        if (data.parent !== null && data.parent !== undefined) {{
                            html += dirItem('&#11014;&#65039;', '..  (voltar)', data.parent, '#f0a500', true);
                        }}
                        if (data.drives) {{
                            data.drives.forEach(function(d) {{
                                html += dirItem('&#128190;', d, d, '#79aec8', false);
                            }});
                        }}
                        if (data.dirs) {{
                            data.dirs.forEach(function(d) {{
                                html += dirItem('&#128193;', d.name, d.path, '#e8e8e8', false);
                            }});
                        }}
                        if (!data.drives && (!data.dirs || data.dirs.length === 0)) {{
                            html = '<div style="color:#555;padding:40px;text-align:center;font-size:14px;">Nenhuma subpasta encontrada.</div>';
                        }}
                        document.getElementById('dir-list').innerHTML = html;
                    }})
                    .catch(function(e) {{
                        document.getElementById('dir-list').innerHTML =
                            '<div style="color:#ff4444;padding:30px;text-align:center;">Erro: ' + e + '</div>';
                    }});
            }};

            function dirItem(icon, label, itemPath, color, isBack) {{
                var escaped = itemPath.replace(/\\\\/g, '\\\\\\\\').replace(/'/g, "\\\\'");
                var bg = isBack ? 'rgba(240,165,0,.06)' : 'transparent';
                var border = isBack ? '1px solid rgba(240,165,0,.2)' : '1px solid transparent';
                return '<div onclick="dirBrowserLoad(\\'' + escaped + '\\')"'
                    + ' style="padding:11px 16px;cursor:pointer;border-radius:8px;margin:2px 0;'
                    + 'display:flex;align-items:center;gap:12px;color:' + color + ';'
                    + 'background:' + bg + ';border:' + border + ';'
                    + 'transition:background .15s,border-color .15s;"'
                    + ' onmouseover="this.style.background=\\'rgba(0,255,200,.09)\\';this.style.borderColor=\\'rgba(0,255,200,.25)\\';"'
                    + ' onmouseout="this.style.background=\\'' + bg + '\\';this.style.borderColor=\\'' + (isBack ? 'rgba(240,165,0,.2)' : 'transparent') + '\\';">'
                    + '<span style="font-size:18px;flex-shrink:0;">' + icon + '</span>'
                    + '<span style="font-size:13px;font-family:monospace;word-break:break-all;">' + label + '</span>'
                    + '</div>';
            }}

            document.addEventListener('keydown', function(e) {{
                if (e.key === 'Escape') dirBrowserClose();
            }});
        }})();
        </script>
        '''
        return mark_safe(html)


class SystemConfigForm(forms.ModelForm):
    class Meta:
        model = SystemConfig
        fields = '__all__'
        widgets = {'media_root': DirectoryPickerWidget()}


def _update_env_media_root(new_path):
    """Grava MEDIA_ROOT no arquivo .env preservando as outras variáveis."""
    env_path = os.path.join(settings.BASE_DIR, 'drive_simulator', '.env')
    if not os.path.isfile(env_path):
        return
    with open(env_path, 'r', encoding='utf-8') as f:
        content = f.read()
    if re.search(r'^MEDIA_ROOT=', content, re.MULTILINE):
        content = re.sub(r'^MEDIA_ROOT=.*$', f'MEDIA_ROOT={new_path}', content, flags=re.MULTILINE)
    else:
        content = content.rstrip('\n') + f'\nMEDIA_ROOT={new_path}\n'
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write(content)


@admin.register(SystemConfig)
class SystemConfigAdmin(admin.ModelAdmin):
    form = SystemConfigForm
    fields = ('media_root', 'updated_at')
    readonly_fields = ('updated_at',)

    def has_add_permission(self, request):
        return not SystemConfig.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def get_urls(self):
        custom = [
            path('browse-dir/', self.admin_site.admin_view(self.browse_directory_view),
                 name='systemconfig_browse_dir'),
        ]
        return custom + super().get_urls()

    def browse_directory_view(self, request):
        raw = request.GET.get('path', '').strip()

        # Windows: raiz sem path → listar drives
        if sys.platform == 'win32' and (not raw or raw in ('/', '\\')):
            import string
            drives = [f'{d}:\\' for d in string.ascii_uppercase
                      if os.path.exists(f'{d}:\\')]
            return JsonResponse({'current': '', 'parent': None, 'dirs': [], 'drives': drives})

        current = os.path.normpath(raw) if raw else ('C:\\' if sys.platform == 'win32' else '/')

        if not os.path.isdir(current):
            current = os.path.dirname(current) or ('C:\\' if sys.platform == 'win32' else '/')

        # Calcula pasta pai
        parent = os.path.dirname(current)
        if parent == current:           # raiz do drive/filesystem
            parent = '' if sys.platform == 'win32' else None

        dirs = []
        try:
            for entry in sorted(os.scandir(current), key=lambda e: e.name.lower()):
                if entry.is_dir(follow_symlinks=False) and not entry.name.startswith('.'):
                    dirs.append({'name': entry.name, 'path': entry.path})
        except PermissionError:
            pass

        return JsonResponse({
            'current': current,
            'parent': parent,
            'dirs': dirs,
        })

    def save_model(self, request, obj, form, change):
        import shutil

        new_path = os.path.normpath(obj.media_root.strip())
        old_path = os.path.normpath(settings.MEDIA_ROOT) if settings.MEDIA_ROOT else None

        obj.media_root = new_path

        # ── Cria novo diretório ────────────────────────────────────────
        try:
            os.makedirs(new_path, exist_ok=True)
        except Exception as e:
            self.message_user(request, f'⚠️ Não foi possível criar o diretório: {e}', level=messages.WARNING)
            return

        # ── Move arquivos do caminho antigo para o novo ────────────────
        moved_count = 0
        move_errors = []

        if old_path and os.path.isdir(old_path) and os.path.normcase(old_path) != os.path.normcase(new_path):
            try:
                for item in os.listdir(old_path):
                    src = os.path.join(old_path, item)
                    dst = os.path.join(new_path, item)
                    try:
                        if os.path.exists(dst):
                            # Destino já existe: mescla subpastas ou pula arquivo duplicado
                            if os.path.isdir(src) and os.path.isdir(dst):
                                for sub in os.listdir(src):
                                    shutil.move(os.path.join(src, sub), os.path.join(dst, sub))
                                os.rmdir(src)
                            else:
                                move_errors.append(f'{item}: já existe no destino, mantido no original')
                                continue
                        else:
                            shutil.move(src, dst)
                        moved_count += 1
                    except Exception as e:
                        move_errors.append(f'{item}: {e}')
            except Exception as e:
                self.message_user(request, f'⚠️ Erro ao listar diretório antigo: {e}', level=messages.WARNING)

        super().save_model(request, obj, form, change)

        # ── Atualiza settings em runtime e .env ───────────────────────
        settings.MEDIA_ROOT = new_path

        try:
            _update_env_media_root(new_path)
        except Exception as e:
            self.message_user(request, f'⚠️ Não foi possível gravar no .env: {e}', level=messages.WARNING)

        # ── Mensagens de resultado ────────────────────────────────────
        if moved_count:
            self.message_user(
                request,
                f'✅ {moved_count} item(ns) movido(s) de "{old_path}" para "{new_path}".',
                level=messages.SUCCESS,
            )
        elif old_path and os.path.normcase(old_path) != os.path.normcase(new_path):
            self.message_user(
                request,
                f'ℹ️ Nenhum arquivo foi movido (diretório antigo vazio ou inexistente).',
                level=messages.INFO,
            )

        for err in move_errors:
            self.message_user(request, f'⚠️ {err}', level=messages.WARNING)

        self.message_user(
            request,
            f'✅ MEDIA_ROOT atualizado para: {new_path}',
            level=messages.SUCCESS,
        )

    def changelist_view(self, request, extra_context=None):
        if not SystemConfig.objects.exists():
            SystemConfig.get()
        return super().changelist_view(request, extra_context)


# Configuração do admin site
admin.site.site_header = "⬡ KnowledgeVault"
admin.site.site_title = "KnowledgeVault Admin"
admin.site.index_title = "⬡ Painel de Administração"