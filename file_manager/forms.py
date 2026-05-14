from django import forms
from .models import Note, Folder, Dork, DorkNote, Tool, ToolNote, Project, ProjectItem, CVE, File
from .models import ResourceLink, YouTubeChannel
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import EmailVerification


class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={
        'class': 'form-control',
        'placeholder': 'Seu email'
    }))
    
    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')
    
    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("Este email já está cadastrado.")
        return email

class VerificationCodeForm(forms.Form):
    code = forms.CharField(
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Digite o código de 6 dígitos'
        })
    )


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True

class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput())
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result

class ResourceLinkForm(forms.ModelForm):
    is_global = forms.BooleanField(
        required=False,
        initial=False,
        label="Tornar link global",
        help_text="Se marcado, este link ficará visível para todos os usuários"
    )
    
    class Meta:
        model = ResourceLink
        fields = ['title', 'url', 'description', 'is_global']

class FileUploadForm(forms.ModelForm):
    folder = forms.ModelChoiceField(
        queryset=Folder.objects.none(),
        required=False,
        label="Enviar para a pasta"
    )

    class Meta:
        model = File
        fields = ['file', 'name', 'folder']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['folder'].queryset = Folder.objects.filter(user=user)

class FileForm(forms.ModelForm):
    is_global = forms.BooleanField(
        required=False,
        initial=False,
        label="Tornar arquivo global (disponível para todos os usuários)",
        help_text="Se marcado, este arquivo ficará visível para todos os usuários do sistema"
    )
    
    class Meta:
        model = File
        fields = ['name', 'file', 'folder', 'is_global']

class FolderForm(forms.ModelForm):
    class Meta:
        model = Folder
        fields = ['name']

class NoteForm(forms.ModelForm):
    is_global = forms.BooleanField(
        required=False,
        initial=False,
        label="Tornar nota global",
        help_text="Se marcado, esta nota ficará visível para todos os usuários"
    )
    
    class Meta:
        model = Note
        fields = ['title', 'content', 'tags', 'folder', 'is_global']

class DorkForm(forms.ModelForm):
    is_global = forms.BooleanField(
        required=False,
        initial=False,
        label="Tornar dork global",
        help_text="Se marcado, este dork ficará visível para todos os usuários"
    )
    
    class Meta:
        model = Dork
        fields = ['query', 'description', 'platform', 'is_global']

class DorkNoteForm(forms.ModelForm):
    class Meta:
        model = DorkNote
        fields = ['note']

class ToolForm(forms.ModelForm):
    is_global = forms.BooleanField(
        required=False,
        initial=False,
        label="Tornar ferramenta global",
        help_text="Se marcado, esta ferramenta ficará visível para todos os usuários"
    )
    
    class Meta:
        model = Tool
        fields = ['name', 'category', 'description', 'homepage', 'is_global']

class ToolNoteForm(forms.ModelForm):
    class Meta:
        model = ToolNote
        fields = ['note']

class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name']

class ProjectItemForm(forms.ModelForm):
    class Meta:
        model = ProjectItem
        fields = ['title', 'file', 'link', 'notes']

class CVEForm(forms.ModelForm):
    is_global = forms.BooleanField(
        required=False,
        initial=False,
        label="Tornar CVE global",
        help_text="Se marcado, esta CVE ficará visível para todos os usuários"
    )
    
    class Meta:
        model = CVE
        fields = ['cve_id', 'description', 'severity', 'references', 'is_global']

class CVEUploadForm(forms.Form):
    files = MultipleFileField(
        label='Selecione arquivos JSON ou CSV',
        help_text='Você pode selecionar múltiplos arquivos'
    )

class ToolImportForm(forms.Form):
    file = forms.FileField(
        label='Arquivo JSON ou CSV',
        help_text='Selecione um arquivo JSON ou CSV com ferramentas'
    )
    is_global = forms.BooleanField(
        required=False,
        initial=False,
        label="Tornar ferramentas importadas globais",
        help_text="Se marcado, todas as ferramentas importadas ficarão visíveis para todos os usuários"
    )

class DorkImportForm(forms.Form):
    file = forms.FileField(
        label='Arquivo CSV de Dorks',
        help_text='Selecione um arquivo CSV com as colunas: query, description, platform'
    )
    is_global = forms.BooleanField(
        required=False,
        initial=False,
        label="Tornar dorks importados globais",
        help_text="Se marcado, todos os dorks importados ficarão visíveis para todos os usuários"
    )

# Formulário para YouTube Channel (se você quiser usar forms Django)
class YouTubeChannelForm(forms.ModelForm):
    is_global = forms.BooleanField(
        required=False,
        initial=False,
        label="Tornar canal global",
        help_text="Se marcado, este canal ficará visível para todos os usuários"
    )
    
    class Meta:
        model = YouTubeChannel
        fields = ['name', 'url', 'description', 'is_global']