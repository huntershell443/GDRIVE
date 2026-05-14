from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib import messages
import requests, time, hashlib
import feedparser
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False
from .models import (File, Note, Folder, Dork, DorkNote, CVE, Tool, ToolNote,
                     Project, ProjectItem, UserStorage, ResourceLink, YouTubeChannel,
                     SharedResource)
from .forms import (NoteForm, FolderForm, DorkForm, DorkNoteForm, ToolImportForm,
                    ToolForm, ToolNoteForm, ProjectForm, ProjectItemForm, CVEForm, FileForm,
                    CVEUploadForm, ResourceLinkForm, DorkImportForm)
from .utils import generate_video_thumbnail, generate_heif_thumbnail, get_server_storage_info, get_folder_storage_usage
from django.core.files import File as DjangoFile
import os
import csv, json
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.http import HttpResponse, JsonResponse
from django.db import models
from django.conf import settings
from django.urls import reverse
from django.views.decorators.http import require_http_methods
import shutil
from datetime import datetime
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.cache import cache
from django.db.models import Count, Q
from django.core.mail import send_mail
from .models import EmailVerification
from .forms import CustomUserCreationForm, VerificationCodeForm
import secrets 
from django.core.mail import EmailMultiAlternatives  
from django.http import HttpResponseNotFound, HttpResponseServerError


ALLOWED_MIME_PREFIXES = (
    'image/', 'video/', 'audio/', 'text/', 'application/pdf',
    'application/zip', 'application/x-zip', 'application/x-rar',
    'application/json', 'application/xml', 'application/msword',
    'application/vnd.', 'application/octet-stream',
)
BLOCKED_MIME_TYPES = (
    'application/x-executable', 'application/x-sharedlib',
    'application/x-dosexec',
)

def validate_file_mime(file_obj):
    """Retorna (ok, mime_type). Bloqueia executáveis detectados pelo conteúdo real."""
    if not MAGIC_AVAILABLE:
        return True, 'unknown'
    try:
        header = file_obj.read(2048)
        file_obj.seek(0)
        mime = magic.from_buffer(header, mime=True)
        if mime in BLOCKED_MIME_TYPES:
            return False, mime
        return True, mime
    except Exception:
        return True, 'unknown'

# ============================================================
# AUTENTICAÇÃO E PÁGINAS PRINCIPAIS
# ============================================================

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = AuthenticationForm(data=request.POST)
        if form.is_valid():
            user = form.get_user()
            
            # Verificar se o email foi verificado
            try:
                verification = EmailVerification.objects.get(user=user)
                if not verification.is_verified:
                    messages.error(request, 'Por favor, verifique seu email antes de fazer login.')
                    return redirect('login')
            except EmailVerification.DoesNotExist:
                # Usuário antigo sem verificação
                pass
            
            login(request, user)
            return redirect('dashboard')
    else:
        form = AuthenticationForm()
    
    return render(request, 'login.html', {'form': form})


def send_verification_email(user_email, verification_code):
    subject = 'Código de Verificação - Sua Plataforma'
    message = f'''
    Olá!
    
    Seu código de verificação para cadastro na plataforma é: {verification_code}
    
    Este código expira em 24 horas.
    
    Se você não solicitou este cadastro, por favor ignore este email.
    
    Atenciosamente,
    Equipe da Plataforma
    '''
    
    try:
        send_mail(
            subject,
            message,
            'noreply@suapplataforma.com',
            [user_email],
            fail_silently=False,
        )
        print(f"✅ Email enviado para {user_email}")
        return True  # ✅ IMPORTANTE: Retornar True quando enviar
    except Exception as e:
        print(f"❌ Erro ao enviar email para {user_email}: {e}")
        return False  # ✅ IMPORTANTE: Retornar False quando falhar

# Usar sem cadastro de email
#def signup_view(request):
#    if request.user.is_authenticated:
#        return redirect('dashboard')

#    if request.method == 'POST':
#        form = CustomUserCreationForm(request.POST)
#        if form.is_valid():
#            user = form.save(commit=False)
#            user.email = form.cleaned_data['email']
#            user.save()

# Criar verificação mas marcar como verificada automaticamente
#            verification, created = EmailVerification.objects.get_or_create(
#                user=user,
#                defaults={'is_verified': True, 'code': '000000'}
#            )

#            messages.success(request, 'Cadastro realizado com sucesso! Faça login.')
#            return redirect('login')
#    else:
#        form = CustomUserCreationForm()

#    return render(request, 'signup.html', {'form': form})

def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            # NÃO salva o usuário ainda, apenas valida os dados
            user_data = {
                'username': form.cleaned_data['username'],
                'email': form.cleaned_data['email'],
                'password': form.cleaned_data['password1'],
            }
            
            # Salvar dados na sessão temporariamente
            request.session['pending_user_data'] = user_data
            request.session['pending_user_created_at'] = str(timezone.now())
            request.session.set_expiry(3600)  # Expira em 1 hora
            
            # Gerar código de verificação
            verification_code = ''.join(secrets.choice('0123456789') for _ in range(6))
            request.session['verification_code'] = verification_code
            request.session['verification_attempts'] = 0  # Contador de tentativas
            
            # Enviar email
            email_sent = send_verification_email(user_data['email'], verification_code)
            
            if email_sent:
                messages.success(request, 'Cadastro iniciado! Verifique seu email para o código de verificação.')
                return redirect('verify_email')
            else:
                # Se não conseguiu enviar email, NÃO mostrar o código
                # Limpar sessão e pedir para tentar novamente
                clear_pending_session(request)
                messages.error(request, 'Erro ao enviar email de verificação. Por favor, tente novamente.')
                return redirect('signup')
    else:
        form = CustomUserCreationForm()
    
    return render(request, 'signup.html', {'form': form})

from django.core.mail import EmailMultiAlternatives

def send_welcome_email_html(user, login_url=None):
    """
    Envia email de boas-vindas em HTML para o usuário após cadastro confirmado
    """
    subject = '🎉 Bem-vindo à Nossa Plataforma!'
    
    # Versão texto simples (fallback)
    text_content = f'''
    Olá {user.username}!

    Seja muito bem-vindo(a) à nossa plataforma!

    Seus dados de acesso:
    • Usuário: {user.username}
    • Email: {user.email}
    • Data de cadastro: {timezone.now().strftime("%d/%m/%Y às %H:%M")}

    Sua conta foi criada com sucesso e já está ativa.

    Recursos disponíveis:
    • Armazenamento de arquivos
    • Gerenciamento de notas
    • Ferramentas de segurança
    • Sistema de CVEs
    • Ferramentas de pesquisa

    Dica de segurança:
    - Mantenha sua senha em local seguro
    - Não compartilhe suas credenciais
    - Use uma senha forte e única

    Atenciosamente,
    Equipe da Plataforma
    '''
    
    # URL do login (usar URL padrão se não for fornecida)
    if not login_url:
        login_url = '/GDriver/login/'
    
    # Versão HTML
    html_content = f'''
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Bem-vindo à Plataforma</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                line-height: 1.6;
                color: #333;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 20px;
            }}
            
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background: white;
                border-radius: 15px;
                overflow: hidden;
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            }}
            
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 40px 30px;
                text-align: center;
            }}
            
            .header h1 {{
                font-size: 32px;
                margin-bottom: 10px;
                font-weight: 700;
            }}
            
            .header p {{
                font-size: 18px;
                opacity: 0.9;
            }}
            
            .content {{
                padding: 40px 30px;
            }}
            
            .welcome {{
                font-size: 24px;
                color: #667eea;
                margin-bottom: 25px;
                text-align: center;
                font-weight: 600;
            }}
            
            .credentials {{
                background: #f8f9fa;
                padding: 25px;
                border-radius: 10px;
                border-left: 5px solid #667eea;
                margin: 25px 0;
            }}
            
            .credential-item {{
                display: flex;
                align-items: center;
                margin-bottom: 15px;
                padding: 10px 0;
            }}
            
            .credential-item:last-child {{
                margin-bottom: 0;
            }}
            
            .credential-icon {{
                font-size: 20px;
                margin-right: 15px;
                width: 30px;
                text-align: center;
            }}
            
            .credential-text {{
                flex: 1;
            }}
            
            .credential-label {{
                font-weight: 600;
                color: #555;
                font-size: 14px;
            }}
            
            .credential-value {{
                font-size: 16px;
                color: #222;
                font-weight: 500;
            }}
            
            .features {{
                margin: 30px 0;
            }}
            
            .features h3 {{
                color: #667eea;
                margin-bottom: 20px;
                font-size: 20px;
                text-align: center;
            }}
            
            .feature-grid {{
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 15px;
                margin-top: 20px;
            }}
            
            .feature-item {{
                display: flex;
                align-items: center;
                padding: 12px;
                background: #f8f9fa;
                border-radius: 8px;
                font-size: 14px;
            }}
            
            .feature-icon {{
                margin-right: 10px;
                font-size: 16px;
            }}
            
            .security-tip {{
                background: #fff3cd;
                padding: 20px;
                border-radius: 10px;
                border-left: 5px solid #ffc107;
                margin: 25px 0;
            }}
            
            .security-tip h4 {{
                color: #856404;
                margin-bottom: 10px;
                display: flex;
                align-items: center;
            }}
            
            .security-tip ul {{
                padding-left: 20px;
                color: #856404;
            }}
            
            .security-tip li {{
                margin-bottom: 5px;
            }}
            
            .footer {{
                text-align: center;
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #eee;
                color: #666;
                font-size: 14px;
            }}
            
            .button {{
                display: block;
                width: 200px;
                margin: 30px auto;
                padding: 12px 25px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                text-decoration: none;
                border-radius: 25px;
                text-align: center;
                font-weight: 600;
                font-size: 16px;
            }}
            
            @media (max-width: 600px) {{
                .feature-grid {{
                    grid-template-columns: 1fr;
                }}
                
                .header h1 {{
                    font-size: 24px;
                }}
                
                .content {{
                    padding: 25px 20px;
                }}
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Cabeçalho -->
            <div class="header">
                <h1>🎉 Bem-vindo!</h1>
                <p>Sua conta foi criada com sucesso</p>
            </div>
            
            <!-- Conteúdo -->
            <div class="content">
                <div class="welcome">
                    Olá, <strong>{user.username}</strong>!
                </div>
                
                <p style="text-align: center; margin-bottom: 25px; color: #555;">
                    Estamos muito felizes em tê-lo(a) conosco! Sua conta foi ativada e já está pronta para uso.
                </p>
                
                <!-- Credenciais -->
                <div class="credentials">
                    <h3 style="color: #667eea; margin-bottom: 20px; text-align: center;">📋 Seus Dados de Acesso</h3>
                    
                    <div class="credential-item">
                        <div class="credential-icon">👤</div>
                        <div class="credential-text">
                            <div class="credential-label">NOME DE USUÁRIO</div>
                            <div class="credential-value">{user.username}</div>
                        </div>
                    </div>
                    
                    <div class="credential-item">
                        <div class="credential-icon">📧</div>
                        <div class="credential-text">
                            <div class="credential-label">EMAIL</div>
                            <div class="credential-value">{user.email}</div>
                        </div>
                    </div>
                    
                    <div class="credential-item">
                        <div class="credential-icon">📅</div>
                        <div class="credential-text">
                            <div class="credential-label">DATA DE CADASTRO</div>
                            <div class="credential-value">{timezone.now().strftime("%d/%m/%Y às %H:%M")}</div>
                        </div>
                    </div>
                </div>
                
                <!-- Botão de Ação -->
                <a href="{login_url}" class="button">
                    🔐 Fazer Login
                </a>
                
                <!-- Recursos -->
                <div class="features">
                    <h3>🚀 Recursos Disponíveis</h3>
                    <div class="feature-grid">
                        <div class="feature-item">
                            <span class="feature-icon">📁</span>
                            Armazenamento de Arquivos
                        </div>
                        <div class="feature-item">
                            <span class="feature-icon">📝</span>
                            Gerenciamento de Notas
                        </div>
                        <div class="feature-item">
                            <span class="feature-icon">🔧</span>
                            Ferramentas de Segurança
                        </div>
                        <div class="feature-item">
                            <span class="feature-icon">🛡️</span>
                            Sistema de CVEs
                        </div>
                        <div class="feature-item">
                            <span class="feature-icon">🔍</span>
                            Ferramentas de Pesquisa
                        </div>
                        <div class="feature-item">
                            <span class="feature-icon">📊</span>
                            Dashboard Personalizado
                        </div>
                    </div>
                </div>
                
                <!-- Dicas de Segurança -->
                <div class="security-tip">
                    <h4>💡 Dicas de Segurança</h4>
                    <ul>
                        <li>Mantenha sua senha em local seguro</li>
                        <li>Não compartilhe suas credenciais de acesso</li>
                        <li>Use uma senha forte e única</li>
                        <li>Ative a verificação em duas etapas se disponível</li>
                        <li>Desconfie de emails suspeitos</li>
                    </ul>
                </div>
                
                <!-- Mensagem Final -->
                <p style="text-align: center; color: #666; line-height: 1.6;">
                    Estamos aqui para ajudar! Se tiver qualquer dúvida ou encontrar algum problema, 
                    não hesite em entrar em contato conosco.
                </p>
            </div>
            
            <!-- Rodapé -->
            <div class="footer">
                <p>Atenciosamente,<br><strong>Equipe da Plataforma</strong></p>
                <p style="margin-top: 10px; font-size: 12px; color: #999;">
                    Este é um email automático, por favor não responda.
                </p>
            </div>
        </div>
    </body>
    </html>
    '''
    
    try:
        email = EmailMultiAlternatives(
            subject,
            text_content,
            'noreply@suapplataforma.com',
            [user.email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        print(f"✅ Email de boas-vindas (HTML) enviado para {user.email}")
        return True
    except Exception as e:
        print(f"❌ Erro ao enviar email de boas-vindas: {e}")
        return False


def verify_email_view(request):
    pending_user_data = request.session.get('pending_user_data')
    verification_code = request.session.get('verification_code')
    
    if not pending_user_data or not verification_code:
        messages.error(request, 'Sessão expirada. Por favor, faça o cadastro novamente.')
        return redirect('signup')
    
    # Verificar se expirou (1 hora)
    created_at_str = request.session.get('pending_user_created_at')
    if created_at_str:
        created_at = timezone.datetime.fromisoformat(created_at_str)
        if timezone.now() > created_at + timezone.timedelta(hours=1):
            # Limpar sessão expirada
            clear_pending_session(request)
            messages.error(request, 'Sessão expirada. Por favor, faça o cadastro novamente.')
            return redirect('signup')
    
    if request.method == 'POST':
        form = VerificationCodeForm(request.POST)
        if form.is_valid():
            entered_code = form.cleaned_data['code']
            
            # Verificar tentativas (máximo 5)
            attempts = request.session.get('verification_attempts', 0)
            if attempts >= 5:
                clear_pending_session(request)
                messages.error(request, 'Muitas tentativas falhas. Por favor, recomece o cadastro.')
                return redirect('signup')
            
            if entered_code == verification_code:
                # ✅ CÓDIGO CORRETO - AGORA SIM CRIAR O USUÁRIO
                try:
                    # Criar usuário
                    user = User.objects.create_user(
                        username=pending_user_data['username'],
                        email=pending_user_data['email'],
                        password=pending_user_data['password'],
                        is_active=True  # Usuário ativo
                    )
                    
                    # Criar registro de verificação
                    EmailVerification.objects.create(
                        user=user,
                        code=verification_code,
                        is_verified=True
                    )
                    
                    # Criar UserStorage para o usuário
                    UserStorage.objects.create(user=user)
                    
                    # 📧 ENVIAR EMAIL DE BOAS-VINDAS EM HTML
                    # Passar a URL completa do login
                    login_url = request.build_absolute_uri('/GDriver/login/')
                    welcome_sent = send_welcome_email_html(user, login_url)
                    
                    # Limpar sessão
                    clear_pending_session(request)
                    
                    if welcome_sent:
                        messages.success(request, '''
                        <div style="text-align: center;">
                            <h4 style="color: #28a745;">🎉 Cadastro realizado com sucesso!</h4>
                            <p>Enviamos um email de boas-vindas com todos os detalhes da sua conta.</p>
                            <p><small>Verifique sua caixa de entrada e spam.</small></p>
                        </div>
                        ''')
                    else:
                        messages.success(request, f'''
                        <div style="text-align: center;">
                            <h4 style="color: #28a745;">✅ Cadastro realizado!</h4>
                            <p style="color: #856404;">Seus dados:<br>
                            <strong>Usuário:</strong> {user.username}<br>
                            <strong>Email:</strong> {user.email}</p>
                        </div>
                        ''')
                    
                    return redirect('login')
                    
                except Exception as e:
                    messages.error(request, f'Erro ao criar usuário: {e}')
                    return redirect('signup')
            
            else:
                # Código incorreto
                request.session['verification_attempts'] = attempts + 1
                remaining_attempts = 5 - (attempts + 1)
                messages.error(request, f'Código inválido. {remaining_attempts} tentativas restantes.')
    else:
        form = VerificationCodeForm()
    
    return render(request, 'verify_email.html', {
        'form': form,
        'email': pending_user_data['email'],
        'attempts': request.session.get('verification_attempts', 0)
    })


def send_verification_email(user_email, verification_code):
    """
    Envia email de verificação em HTML
    """
    subject = '🔐 Código de Verificação - Sua Plataforma'
    
    # Versão texto simples
    text_content = f'''
    Olá!

    Seu código de verificação para cadastro na plataforma é: {verification_code}

    Este código expira em 24 horas.

    Se você não solicitou este cadastro, por favor ignore este email.

    Atenciosamente,
    Equipe da Plataforma
    '''
    
    # Versão HTML
    html_content = f'''
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Código de Verificação</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                margin: 0;
                padding: 20px;
                color: #333;
            }}
            .container {{
                max-width: 500px;
                margin: 0 auto;
                background: white;
                border-radius: 15px;
                overflow: hidden;
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
            }}
            .header {{
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }}
            .header h1 {{
                margin: 0;
                font-size: 24px;
            }}
            .content {{
                padding: 30px;
            }}
            .code-container {{
                background: #f8f9fa;
                padding: 25px;
                border-radius: 10px;
                text-align: center;
                margin: 20px 0;
                border: 2px dashed #667eea;
            }}
            .verification-code {{
                font-size: 42px;
                font-weight: bold;
                color: #667eea;
                letter-spacing: 8px;
                font-family: 'Courier New', monospace;
            }}
            .footer {{
                text-align: center;
                padding: 20px;
                background: #f8f9fa;
                color: #666;
                font-size: 14px;
            }}
            .warning {{
                background: #fff3cd;
                padding: 15px;
                border-radius: 8px;
                border-left: 4px solid #ffc107;
                margin: 20px 0;
                color: #856404;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔐 Verificação de Email</h1>
            </div>
            
            <div class="content">
                <p>Olá!</p>
                
                <p>Use o código abaixo para completar seu cadastro na plataforma:</p>
                
                <div class="code-container">
                    <div class="verification-code">{verification_code}</div>
                </div>
                
                <div class="warning">
                    <strong>⚠️ Importante:</strong> Este código expira em 24 horas.
                </div>
                
                <p>Se você não solicitou este cadastro, por favor ignore este email.</p>
            </div>
            
            <div class="footer">
                <p>Atenciosamente,<br><strong>Equipe da Plataforma</strong></p>
            </div>
        </div>
    </body>
    </html>
    '''
    
    try:
        email = EmailMultiAlternatives(
            subject,
            text_content,
            'noreply@suapplataforma.com',
            [user_email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        print(f"✅ Email de verificação (HTML) enviado para {user_email}")
        return True
    except Exception as e:
        print(f"❌ Erro ao enviar email de verificação: {e}")
        return False

def send_account_reminder_email_html(user_email):
    """
    Envia lembrete dos dados de conta em HTML
    """
    try:
        user = User.objects.get(email=user_email)
        
        subject = '🔐 Seus Dados de Acesso - Plataforma'
        
        text_content = f'''
        Olá {user.username}!

        Seguem seus dados de acesso na plataforma:

        Usuário: {user.username}
        Email: {user.email}
        Data de cadastro: {user.date_joined.strftime("%d/%m/%Y")}

        Se você não solicitou esta informação, por favor ignore este email.

        Atenciosamente,
        Equipe da Plataforma
        '''
        
        html_content = f'''
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    background: #f4f4f4;
                    padding: 20px;
                }}
                .container {{
                    max-width: 500px;
                    margin: 0 auto;
                    background: white;
                    border-radius: 10px;
                    padding: 30px;
                    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
                }}
                .header {{
                    text-align: center;
                    color: #667eea;
                    margin-bottom: 30px;
                }}
                .credentials {{
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    margin: 20px 0;
                }}
                .footer {{
                    text-align: center;
                    margin-top: 30px;
                    color: #666;
                    font-size: 14px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>🔐 Seus Dados de Acesso</h1>
                </div>
                
                <p>Olá <strong>{user.username}</strong>,</p>
                
                <p>Aqui estão seus dados de acesso na plataforma:</p>
                
                <div class="credentials">
                    <p><strong>👤 Usuário:</strong> {user.username}</p>
                    <p><strong>📧 Email:</strong> {user.email}</p>
                    <p><strong>📅 Data de cadastro:</strong> {user.date_joined.strftime("%d/%m/%Y")}</p>
                </div>
                
                <p><em>Se você não solicitou esta informação, por favor ignore este email.</em></p>
            </div>
            
            <div class="footer">
                <p>Atenciosamente,<br>Equipe da Plataforma</p>
            </div>
        </body>
        </html>
        '''
        
        email = EmailMultiAlternatives(
            subject,
            text_content,
            'noreply@suapplataforma.com',
            [user_email]
        )
        email.attach_alternative(html_content, "text/html")
        email.send()
        
        print(f"✅ Lembrete de conta (HTML) enviado para {user_email}")
        return True
        
    except User.DoesNotExist:
        print(f"❌ Usuário não encontrado para email: {user_email}")
        return False
    except Exception as e:
        print(f"❌ Erro ao enviar lembrete: {e}")
        return False

def clear_pending_session(request):
    """Limpa dados temporários da sessão"""
    keys_to_remove = [
        'pending_user_data', 
        'verification_code', 
        'pending_user_created_at',
        'verification_attempts'
    ]
    for key in keys_to_remove:
        if key in request.session:
            del request.session[key]

def resend_verification_code(request):
    pending_user_data = request.session.get('pending_user_data')
    
    if not pending_user_data:
        messages.error(request, 'Sessão expirada.')
        return redirect('signup')
    
    # Gerar novo código
    new_code = ''.join(secrets.choice('0123456789') for _ in range(6))
    request.session['verification_code'] = new_code
    request.session['verification_attempts'] = 0  # Resetar tentativas
    
    # Enviar email
    email_sent = send_verification_email(pending_user_data['email'], new_code)
    
    if email_sent:
        messages.success(request, 'Novo código enviado para seu email!')
    else:
        # Se falhar, NÃO mostrar o código
        messages.error(request, 'Erro ao reenviar código. Tente novamente.')
    
    return redirect('verify_email')



@login_required
def logout_view(request):
    logout(request)
    return redirect('login')

@login_required
def dashboard_view(request):
    # Recursos próprios
    resource_links = ResourceLink.objects.filter(user=request.user)
    files = File.objects.filter(user=request.user)
    notes = Note.objects.filter(user=request.user)
    dorks = Dork.objects.filter(user=request.user)
    cves = CVE.objects.filter(user=request.user)
    projects = Project.objects.filter(user=request.user)
    user_channels = YouTubeChannel.objects.filter(user=request.user)
    
    # FERRAMENTAS - Incluir próprias + compartilhadas + globais
    user_tools = Tool.objects.filter(user=request.user)
    
    # Ferramentas compartilhadas com este usuário (SharedResource)
    shared_tools_ids = SharedResource.objects.filter(
        resource_type='tool',
        shared_with=request.user
    ).values_list('resource_id', flat=True)
    
    # Ferramentas compartilhadas publicamente (SharedResource)
    public_tools_ids = SharedResource.objects.filter(
        resource_type='tool',
        shared_with_all=True
    ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
    
    # Ferramentas globais (is_global=True)
    global_tools = Tool.objects.filter(is_global=True).exclude(user=request.user)
    
    all_shared_tools_ids = list(shared_tools_ids) + list(public_tools_ids)
    shared_tools = Tool.objects.filter(id__in=all_shared_tools_ids) if all_shared_tools_ids else Tool.objects.none()
    
    # Combinar ferramentas próprias, compartilhadas e globais
    all_tools = (user_tools | shared_tools | global_tools).distinct()
    
    # CVEs - Incluir próprias + compartilhadas + globais
    user_cves = CVE.objects.filter(user=request.user)
    
    # CVEs compartilhadas com este usuário (SharedResource)
    shared_cves_ids = SharedResource.objects.filter(
        resource_type='cve',
        shared_with=request.user
    ).values_list('resource_id', flat=True)
    
    # CVEs compartilhadas publicamente (SharedResource)
    public_cves_ids = SharedResource.objects.filter(
        resource_type='cve',
        shared_with_all=True
    ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
    
    # CVEs globais (is_global=True)
    global_cves = CVE.objects.filter(is_global=True).exclude(user=request.user)
    
    all_shared_cves_ids = list(shared_cves_ids) + list(public_cves_ids)
    shared_cves = CVE.objects.filter(id__in=all_shared_cves_ids) if all_shared_cves_ids else CVE.objects.none()
    
    # Combinar CVEs próprias, compartilhadas e globais
    all_cves = (user_cves | shared_cves | global_cves).distinct()
    
    # DORKS - Incluir próprios + compartilhados + globais
    user_dorks = Dork.objects.filter(user=request.user)
    
    # Dorks compartilhados com este usuário (SharedResource)
    shared_dorks_ids = SharedResource.objects.filter(
        resource_type='dork',
        shared_with=request.user
    ).values_list('resource_id', flat=True)
    
    # Dorks compartilhados publicamente (SharedResource)
    public_dorks_ids = SharedResource.objects.filter(
        resource_type='dork',
        shared_with_all=True
    ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
    
    # Dorks globais (is_global=True)
    global_dorks = Dork.objects.filter(is_global=True).exclude(user=request.user)
    
    all_shared_dorks_ids = list(shared_dorks_ids) + list(public_dorks_ids)
    shared_dorks = Dork.objects.filter(id__in=all_shared_dorks_ids) if all_shared_dorks_ids else Dork.objects.none()
    
    # Combinar dorks próprios, compartilhados e globais
    all_dorks = (user_dorks | shared_dorks | global_dorks).distinct()
    
    # ARQUIVOS - Incluir próprios + compartilhados + globais
    user_files = File.objects.filter(user=request.user)
    
    # Arquivos compartilhados com este usuário (SharedResource)
    shared_files_ids = SharedResource.objects.filter(
        resource_type='file',
        shared_with=request.user
    ).values_list('resource_id', flat=True)
    
    # Arquivos compartilhados publicamente (SharedResource)
    public_files_ids = SharedResource.objects.filter(
        resource_type='file',
        shared_with_all=True
    ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
    
    # Arquivos globais (is_global=True)
    global_files = File.objects.filter(is_global=True).exclude(user=request.user)
    
    all_shared_files_ids = list(shared_files_ids) + list(public_files_ids)
    shared_files = File.objects.filter(id__in=all_shared_files_ids) if all_shared_files_ids else File.objects.none()
    
    # Combinar arquivos próprios, compartilhados e globais
    all_files = (user_files | shared_files | global_files).distinct()
    
    # LINKS - Incluir próprios + compartilhados + globais
    user_links = ResourceLink.objects.filter(user=request.user)
    
    # Links compartilhados com este usuário (SharedResource)
    shared_links_ids = SharedResource.objects.filter(
        resource_type='resource_link',
        shared_with=request.user
    ).values_list('resource_id', flat=True)
    
    # Links compartilhados publicamente (SharedResource)
    public_links_ids = SharedResource.objects.filter(
        resource_type='resource_link',
        shared_with_all=True
    ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
    
    # Links globais (is_global=True)
    global_links = ResourceLink.objects.filter(is_global=True).exclude(user=request.user)
    
    all_shared_links_ids = list(shared_links_ids) + list(public_links_ids)
    shared_links = ResourceLink.objects.filter(id__in=all_shared_links_ids) if all_shared_links_ids else ResourceLink.objects.none()
    
    # Combinar links próprios, compartilhados e globais
    all_links = (user_links | shared_links | global_links).distinct()
    
    # Canais - Incluir próprios + compartilhados + globais
    user_channels = YouTubeChannel.objects.filter(user=request.user)
    
    # Canais compartilhados com este usuário (SharedResource)
    shared_channels_ids = SharedResource.objects.filter(
        resource_type='youtube_channel',
        shared_with=request.user
    ).values_list('resource_id', flat=True)
    
    # Canais compartilhados publicamente (SharedResource)
    public_channels_ids = SharedResource.objects.filter(
        resource_type='youtube_channel',
        shared_with_all=True
    ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
    
    # Canais globais (is_global=True)
    global_channels = YouTubeChannel.objects.filter(is_global=True).exclude(user=request.user)
    
    all_shared_channels_ids = list(shared_channels_ids) + list(public_channels_ids)
    shared_channels = YouTubeChannel.objects.filter(id__in=all_shared_channels_ids) if all_shared_channels_ids else YouTubeChannel.objects.none()
    
    # Combinar canais próprios, compartilhados e globais
    all_channels = (user_channels | shared_channels | global_channels).distinct()
    
    rss_feeds_pt = ['https://olhardigital.com.br/feed/']
    rss_feed_en = 'https://www.securityweek.com/feed'
    
    def parse_multiple_feeds(urls):
        all_items = []
        for url in urls:
            feed = feedparser.parse(url)
            for entry in feed.entries[:3]:
                try:
                    published_dt = datetime(*entry.published_parsed[:6])
                    published_str = published_dt.strftime('%Y-%m-%d %H:%M')
                except:
                    published_str = ''
                all_items.append({
                    'title': entry.title,
                    'link': entry.link,
                    'published': published_str,
                })
        return sorted(all_items, key=lambda x: x['published'], reverse=True)[:10]
    
    def parse_feed(url):
        feed = feedparser.parse(url)
        items = []
        for entry in feed.entries[:5]:
            try:
                published_dt = datetime(*entry.published_parsed[:6])
                published_str = published_dt.strftime('%Y-%m-%d %H:%M')
            except:
                published_str = ''
            items.append({
                'title': entry.title,
                'link': entry.link,
                'published': published_str,
            })
        return items
    
    news_pt = parse_multiple_feeds(rss_feeds_pt)
    news_en = parse_feed(rss_feed_en)
    
    context = {
        'resource_links': all_links,
        'files': all_files,
        'notes': notes,  # Mantenha apenas as próprias para notas, ou adicione lógica similar se quiser
        'dorks': all_dorks,
        'cves': all_cves,
        'tools': all_tools,
        'projects': projects,
        'channels': all_channels,
        
        # Contagens para o template
        'user_channels_count': user_channels.count(),
        'shared_channels_count': shared_channels.count() + global_channels.count(),
        
        'user_tools_count': user_tools.count(),
        'shared_tools_count': shared_tools.count() + global_tools.count(),
        
        'user_cves_count': user_cves.count(),
        'shared_cves_count': shared_cves.count() + global_cves.count(),
        
        'user_dorks_count': user_dorks.count(),
        'shared_dorks_count': shared_dorks.count() + global_dorks.count(),
        
        'user_files_count': user_files.count(),
        'shared_files_count': shared_files.count() + global_files.count(),
        
        'user_links_count': user_links.count(),
        'shared_links_count': shared_links.count() + global_links.count(),

        'news_pt': news_pt,
        'news_en': news_en,
    }

    # Contagens da Análise Binária (app opcional)
    try:
        from binary_analyzer.models import BinaryAnalysis
        ba_qs = BinaryAnalysis.objects.filter(file__user=request.user)
        context['binary_analyses_count']  = ba_qs.count()
        context['binary_high_risk_count'] = ba_qs.filter(status='done', risk_score__gte=75).count()
        context['binary_pending_count']   = ba_qs.filter(status__in=['pending', 'analyzing']).count()
    except Exception:
        context['binary_analyses_count']  = 0
        context['binary_high_risk_count'] = 0
        context['binary_pending_count']   = 0

    return render(request, 'dashboard.html', context)

@login_required
def search_all(request):
    query = request.GET.get('q', '').strip()
    platform = request.GET.get('dork_platform')
    page = request.GET.get('page', 1)
    
    def paginate(queryset):
        paginator = Paginator(queryset, 25)
        return paginator.get_page(page)
    
    if not query:
        files = paginate(File.objects.none())
        notes = paginate(Note.objects.none())
        cves = paginate(CVE.objects.none())
        projects = paginate(Project.objects.none())
        dorks = paginate(Dork.objects.none())
        tools = paginate(Tool.objects.none())
        resource_links = paginate(ResourceLink.objects.none())
        channels = paginate(YouTubeChannel.objects.none())
    else:
        # ARQUIVOS - Incluir próprios + compartilhados + globais
        user_files = File.objects.filter(user=request.user)
        shared_files_ids = SharedResource.objects.filter(
            resource_type='file', shared_with=request.user
        ).values_list('resource_id', flat=True)
        public_files_ids = SharedResource.objects.filter(
            resource_type='file', shared_with_all=True
        ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
        global_files = File.objects.filter(is_global=True).exclude(user=request.user)
        all_shared_files_ids = list(shared_files_ids) + list(public_files_ids)
        shared_files = File.objects.filter(id__in=all_shared_files_ids) if all_shared_files_ids else File.objects.none()
        all_files = (user_files | shared_files | global_files).distinct()
        files_qs = all_files.filter(
            Q(name__icontains=query) | Q(folder__icontains=query)
        )
        
        # NOTAS - Incluir próprias + compartilhadas + globais
        user_notes = Note.objects.filter(user=request.user)
        shared_notes_ids = SharedResource.objects.filter(
            resource_type='note', shared_with=request.user
        ).values_list('resource_id', flat=True)
        public_notes_ids = SharedResource.objects.filter(
            resource_type='note', shared_with_all=True
        ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
        global_notes = Note.objects.filter(is_global=True).exclude(user=request.user)
        all_shared_notes_ids = list(shared_notes_ids) + list(public_notes_ids)
        shared_notes = Note.objects.filter(id__in=all_shared_notes_ids) if all_shared_notes_ids else Note.objects.none()
        all_notes = (user_notes | shared_notes | global_notes).distinct()
        notes_qs = all_notes.filter(
            Q(title__icontains=query) | Q(content__icontains=query) | Q(tags__icontains=query)
        )
        
        # CVEs - Incluir próprias + globais
        user_cves = CVE.objects.filter(user=request.user)
        global_cves = CVE.objects.filter(is_global=True).exclude(user=request.user)
        all_cves = (user_cves | global_cves).distinct()
        cves_qs = all_cves.filter(
            Q(cve_id__icontains=query) | Q(description__icontains=query)
        )
        
        # PROJETOS - Apenas próprios
        projects_qs = Project.objects.filter(user=request.user).filter(
            Q(name__icontains=query) | Q(projectitem__title__icontains=query) | Q(projectitem__notes__icontains=query)
        ).distinct()
        
        # DORKS - Incluir próprios + compartilhados + globais
        user_dorks = Dork.objects.filter(user=request.user)
        shared_dorks_ids = SharedResource.objects.filter(
            resource_type='dork', shared_with=request.user
        ).values_list('resource_id', flat=True)
        public_dorks_ids = SharedResource.objects.filter(
            resource_type='dork', shared_with_all=True
        ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
        global_dorks = Dork.objects.filter(is_global=True).exclude(user=request.user)
        all_shared_dorks_ids = list(shared_dorks_ids) + list(public_dorks_ids)
        shared_dorks = Dork.objects.filter(id__in=all_shared_dorks_ids) if all_shared_dorks_ids else Dork.objects.none()
        all_dorks = (user_dorks | shared_dorks | global_dorks).distinct()
        dorks_qs = all_dorks.filter(
            Q(query__icontains=query) | Q(description__icontains=query)
        )
        if platform:
            dorks_qs = dorks_qs.filter(platform__icontains=platform)
        
        # FERRAMENTAS - Incluir próprias + compartilhadas + globais
        user_tools = Tool.objects.filter(user=request.user)
        shared_tools_ids = SharedResource.objects.filter(
            resource_type='tool', shared_with=request.user
        ).values_list('resource_id', flat=True)
        public_tools_ids = SharedResource.objects.filter(
            resource_type='tool', shared_with_all=True
        ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
        global_tools = Tool.objects.filter(is_global=True).exclude(user=request.user)
        all_shared_tools_ids = list(shared_tools_ids) + list(public_tools_ids)
        shared_tools = Tool.objects.filter(id__in=all_shared_tools_ids) if all_shared_tools_ids else Tool.objects.none()
        all_tools = (user_tools | shared_tools | global_tools).distinct()
        tools_qs = all_tools.filter(
            Q(name__icontains=query) | Q(category__icontains=query) | Q(description__icontains=query)
        )
        
        # LINKS - Incluir próprios + compartilhados + globais
        user_links = ResourceLink.objects.filter(user=request.user)
        shared_links_ids = SharedResource.objects.filter(
            resource_type='resource_link', shared_with=request.user
        ).values_list('resource_id', flat=True)
        public_links_ids = SharedResource.objects.filter(
            resource_type='resource_link', shared_with_all=True
        ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
        global_links = ResourceLink.objects.filter(is_global=True).exclude(user=request.user)
        all_shared_links_ids = list(shared_links_ids) + list(public_links_ids)
        shared_links = ResourceLink.objects.filter(id__in=all_shared_links_ids) if all_shared_links_ids else ResourceLink.objects.none()
        all_links = (user_links | shared_links | global_links).distinct()
        resource_links_qs = all_links.filter(
            Q(title__icontains=query) | Q(description__icontains=query) | Q(url__icontains=query)
        )
        
        # CANAIS - Incluir próprios + compartilhados + globais
        user_channels = YouTubeChannel.objects.filter(user=request.user)
        shared_channels_ids = SharedResource.objects.filter(
            resource_type='youtube_channel', shared_with=request.user
        ).values_list('resource_id', flat=True)
        public_channels_ids = SharedResource.objects.filter(
            resource_type='youtube_channel', shared_with_all=True
        ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
        global_channels = YouTubeChannel.objects.filter(is_global=True).exclude(user=request.user)
        all_shared_channels_ids = list(shared_channels_ids) + list(public_channels_ids)
        shared_channels = YouTubeChannel.objects.filter(id__in=all_shared_channels_ids) if all_shared_channels_ids else YouTubeChannel.objects.none()
        all_channels = (user_channels | shared_channels | global_channels).distinct()
        channels_qs = all_channels.filter(
            Q(name__icontains=query) | Q(description__icontains=query)
        )
        
        files = paginate(files_qs)
        notes = paginate(notes_qs)
        cves = paginate(cves_qs)
        projects = paginate(projects_qs)
        dorks = paginate(dorks_qs)
        tools = paginate(tools_qs)
        resource_links = paginate(resource_links_qs)
        channels = paginate(channels_qs)
    
    groups = [
        ('📂 Arquivos', files),
        ('📝 Notas', notes),
        ('🛡️ CVEs', cves),
        ('📁 Projetos', projects),
        ('🧠 Dorks', dorks),
        ('🧰 Ferramentas', tools),
        ('🔗 Links úteis', resource_links),
        ('📺 Canais YouTube', channels),
    ]
    
    all_empty = all(not group[1] for group in groups)
    
    return render(request, 'search_results.html', {
        'query': query,
        'platform': platform,
        'groups': groups,
        'all_empty': all_empty,
    })

# ============================================================
# GERENCIAMENTO DE ARQUIVOS E PASTAS
# ============================================================

@login_required
def file_list(request):
    query = request.GET.get('q')
    selected_folder_id = request.GET.get('folder')
    
    # ARQUIVOS PRÓPRIOS
    user_files = File.objects.filter(user=request.user)
    
    # Arquivos compartilhados com este usuário (SharedResource)
    shared_files_ids = SharedResource.objects.filter(
        resource_type='file',
        shared_with=request.user
    ).values_list('resource_id', flat=True)
    
    # Arquivos compartilhados publicamente (SharedResource)
    public_files_ids = SharedResource.objects.filter(
        resource_type='file',
        shared_with_all=True
    ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
    
    # Arquivos globais (is_global=True)
    global_files = File.objects.filter(is_global=True).exclude(user=request.user)
    
    all_shared_ids = list(shared_files_ids) + list(public_files_ids)
    shared_files = File.objects.filter(id__in=all_shared_ids) if all_shared_ids else File.objects.none()
    
    # COMBINAR: próprios + compartilhados + globais
    all_files = (user_files | shared_files | global_files).distinct()
    
    # ============================================================
    # CRIAÇÃO AUTOMÁTICA DA PASTA DE COMPARTILHAMENTOS
    # ============================================================
    shares_folder, created = Folder.objects.get_or_create(
        name="COMPARTILHAMENTOS",
        parent=None,
        user=request.user,
        defaults={'name': 'COMPARTILHAMENTOS'}
    )
    
    if created:
        try:
            shares_folder.create_physical_folder()
            print(f"Pasta COMPARTILHAMENTOS criada para usuário {request.user.username}")
        except Exception as e:
            print(f"Erro ao criar pasta COMPARTILHAMENTOS: {e}")
    
    # Processar arquivos compartilhados para criar estrutura de pastas
    process_shared_files_structure(request.user, shares_folder, shared_files)
    process_shared_files_structure(request.user, shares_folder, global_files)
    # ============================================================
    
    if query:
        files = all_files.filter(
            Q(name__icontains=query) |
            Q(folder__icontains=query)
        ).order_by('name')
        
        subfolders = Folder.objects.filter(user=request.user, parent__isnull=True)
        selected_folder = None
        all_folders = Folder.objects.filter(user=request.user)
        is_global_search = True
    else:
        if selected_folder_id:
            selected_folder = Folder.objects.filter(id=selected_folder_id, user=request.user).first()
            files = all_files.filter(folder=selected_folder.name)
            subfolders = Folder.objects.filter(user=request.user, parent=selected_folder)
            all_folders = Folder.objects.filter(user=request.user).exclude(id=selected_folder_id)
        else:
            files = all_files.filter(folder__isnull=True)
            subfolders = Folder.objects.filter(user=request.user, parent__isnull=True)
            all_folders = Folder.objects.filter(user=request.user)
            selected_folder = None
        is_global_search = False
    
    total_storage_used = get_user_storage_usage(request.user)
    
    valid_files = []
    missing_files = []

    for file in files:
        if file.file and os.path.isfile(file.file.path):
            valid_files.append(file)
        else:
            missing_files.append(file)

    if missing_files:
        messages.warning(
            request,
            f"⚠️ {len(missing_files)} arquivo(s) não encontrado(s) no disco. "
            f"Verifique se o MEDIA_ROOT está correto — os registros foram mantidos."
        )

    files = valid_files

    paginator = Paginator(files, 30)
    page_number = request.GET.get('page', 1)
    try:
        files_page = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        files_page = paginator.page(1)

    user_storage, created = UserStorage.objects.get_or_create(user=request.user)
    max_storage = user_storage.get_storage_limit_bytes()
    percent_used = (total_storage_used / max_storage) * 100 if max_storage > 0 else 0
    remaining_storage = max_storage - total_storage_used
    
    folder_used = get_folder_storage_usage(settings.MEDIA_ROOT)
    folder_disk = shutil.disk_usage(str(settings.MEDIA_ROOT))
    folder_free = folder_disk.free
    folder_total = folder_used + folder_free
    
    server_storage = {
        'total': folder_total,
        'used': folder_used,
        'free': folder_free
    }
    
    return render(request, 'file_list.html', {
        'folders': all_folders,
        'subfolders': subfolders,
        'files': files_page,
        'paginator': paginator,
        'page_obj': files_page,
        'query': query,
        'total_storage_used': total_storage_used,
        'remaining_storage': remaining_storage,
        'percent_used': percent_used,
        'max_storage': max_storage,
        'server_storage': server_storage,
        'selected_folder_id': selected_folder_id,
        'selected_folder': selected_folder,
        'is_search': bool(query),
        'is_global_search': is_global_search,
        'user_files_count': user_files.count(),
        'shared_files_count': shared_files.count() + global_files.count(),
        'shares_folder': shares_folder  # Adiciona a pasta de compartilhamentos ao contexto
    })

def process_shared_files_structure(user, shares_folder, shared_files):
    """
    Processa arquivos compartilhados e cria a estrutura de pastas correspondente
    dentro da pasta COMPARTILHAMENTOS
    """
    for shared_file in shared_files:
        if shared_file.folder:
            # Se o arquivo compartilhado está em uma pasta, criar a estrutura correspondente
            create_shared_folder_structure(user, shares_folder, shared_file.folder, shared_file)

def create_shared_folder_structure(user, parent_folder, folder_path, shared_file):
    """
    Cria recursivamente a estrutura de pastas para arquivos compartilhados
    """
    if not folder_path:
        return parent_folder
    
    # Separar o caminho da pasta em partes
    folder_parts = folder_path.split('/')
    current_folder = parent_folder
    
    for folder_name in folder_parts:
        if folder_name.strip():  # Ignorar strings vazias
            # Criar ou obter a subpasta
            subfolder, created = Folder.objects.get_or_create(
                name=folder_name,
                parent=current_folder,
                user=user,
                defaults={'name': folder_name}
            )
            
            if created:
                try:
                    subfolder.create_physical_folder()
                except Exception as e:
                    print(f"Erro ao criar subpasta {folder_name}: {e}")
            
            current_folder = subfolder
    
    return current_folder

def update_shared_file_structure(user, file_instance):
    """
    Atualiza a estrutura de pastas de compartilhamento quando um arquivo é compartilhado
    """
    try:
        # Encontrar ou criar a pasta COMPARTILHAMENTOS
        shares_folder, created = Folder.objects.get_or_create(
            name="COMPARTILHAMENTOS",
            parent=None,
            user=user,
            defaults={'name': 'COMPARTILHAMENTOS'}
        )
        
        if created:
            shares_folder.create_physical_folder()
        
        # Se o arquivo tem um caminho de pasta, criar a estrutura
        if file_instance.folder:
            create_shared_folder_structure(user, shares_folder, file_instance.folder, file_instance)
            
    except Exception as e:
        print(f"Erro ao atualizar estrutura de compartilhamento: {e}")


def get_user_storage_usage(user):
    """Calcula o uso total de armazenamento de um usuário incluindo TODOS os arquivos"""
    total_size = 0
    
    user_files = File.objects.filter(user=user)
    
    for file in user_files:
        if file.file and os.path.isfile(file.file.path):
            try:
                total_size += file.file.size
            except (OSError, ValueError):
                continue
    
    return total_size

@login_required
def create_folder(request):
    if request.method == 'POST':
        name = request.POST.get('folder_name')
        parent_id = request.POST.get('parent_folder')
        
        if name:
            parent_folder = None
            if parent_id:
                parent_folder = get_object_or_404(Folder, id=parent_id, user=request.user)
            
            folder, created = Folder.objects.get_or_create(
                name=name, 
                parent=parent_folder,
                user=request.user
            )
            
            if created:
                try:
                    folder.create_physical_folder()
                    messages.success(request, f'Pasta "{name}" criada com sucesso!')
                except Exception as e:
                    folder.delete()
                    messages.error(request, f'Erro ao criar pasta física: {e}')
            else:
                messages.info(request, f'Pasta "{name}" já existe!')
    
    return redirect('file_list')

@login_required
def move_folder(request, folder_id):
    if request.method == 'POST':
        folder = get_object_or_404(Folder, id=folder_id, user=request.user)
        new_parent_id = request.POST.get('new_parent_id')
        
        new_parent = None
        if new_parent_id:
            new_parent = get_object_or_404(Folder, id=new_parent_id, user=request.user)
            
            if new_parent.id == folder.id:
                messages.error(request, "Não é possível mover uma pasta para dentro de si mesma!")
                return redirect('file_list')
            
            current = new_parent
            while current:
                if current.id == folder.id:
                    messages.error(request, "Não é possível mover uma pasta para dentro de um de seus subdiretórios!")
                    return redirect('file_list')
                current = current.parent
        
        try:
            folder.move_physical_folder(new_parent)
            messages.success(request, f"Pasta '{folder.name}' movida com sucesso!")
        except Exception as e:
            messages.error(request, f"Erro ao mover pasta: {e}")
    
    return redirect('file_list')

@login_required
@require_http_methods(["POST", "GET"])
def delete_folder(request, folder_id):
    """Exclui pasta - CORRIGIDA"""
    folder = get_object_or_404(Folder, id=folder_id, user=request.user)
    folder_name = folder.name
    
    try:
        # Verificar se a pasta está vazia
        files_in_folder = File.objects.filter(user=request.user, folder=folder.name)
        subfolders = Folder.objects.filter(user=request.user, parent=folder)
        
        if files_in_folder.exists() or subfolders.exists():
            error_message = f"A pasta '{folder_name}' não está vazia. Remova primeiro os arquivos e subpastas."
            
            if request.headers.get('x-requested-with') == 'XMLHttpRequest':
                return JsonResponse({
                    "success": False,
                    "message": error_message
                })
            else:
                messages.error(request, error_message)
                return redirect('file_list')
        
        # Excluir pasta física e do banco
        folder.delete_physical_folder()
        folder.delete()
        
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                "success": True,
                "message": f"Pasta '{folder_name}' excluída com sucesso!"
            })
        else:
            messages.success(request, f"Pasta '{folder_name}' excluída com sucesso!")
            
    except Exception as e:
        error_message = f"Erro ao excluir pasta: {str(e)}"
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({
                "success": False,
                "message": error_message
            })
        else:
            messages.error(request, error_message)
    
    return redirect('file_list')

@login_required
def check_file_exists(request, file_id):
    """Verifica se um arquivo existe fisicamente - CORRIGIDA"""
    try:
        # Buscar arquivo entre próprios + compartilhados + globais
        user_files = File.objects.filter(user=request.user)
        shared_files_ids = SharedResource.objects.filter(
            resource_type='file', shared_with=request.user
        ).values_list('resource_id', flat=True)
        public_files_ids = SharedResource.objects.filter(
            resource_type='file', shared_with_all=True
        ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
        global_files = File.objects.filter(is_global=True).exclude(user=request.user)
        
        all_shared_ids = list(shared_files_ids) + list(public_files_ids)
        shared_files = File.objects.filter(id__in=all_shared_ids) if all_shared_ids else File.objects.none()
        
        # Combinar todos os arquivos acessíveis
        all_files = (user_files | shared_files | global_files).distinct()
        
        file = get_object_or_404(all_files, id=file_id)
        
        exists = file.file and os.path.isfile(file.file.path)
        
        return JsonResponse({
            'exists': exists,
            'file_name': file.name,
            'file_path': file.file.path if file.file else None,
            'can_delete': file.user == request.user  # Só o dono pode excluir
        })
        
    except Exception as e:
        return JsonResponse({
            'error': str(e),
            'exists': False
        }, status=404)

@login_required
def delete_files(request):
    """Exclui arquivos - CORRIGIDA com verificação de permissão"""
    ids = request.POST.getlist('selected_files')
    
    deleted_count = 0
    error_files = []
    permission_denied = []
    
    for file_id in ids:
        try:
            file = File.objects.get(id=file_id, user=request.user)

            try:
                if file.file and file.file.name and os.path.isfile(file.file.path):
                    os.remove(file.file.path)
            except Exception:
                pass

            try:
                if file.thumbnail and file.thumbnail.name and os.path.isfile(file.thumbnail.path):
                    os.remove(file.thumbnail.path)
            except Exception:
                pass

            file.delete()
            deleted_count += 1

        except File.DoesNotExist:
            permission_denied.append(f"ID {file_id}")
        except Exception as e:
            error_files.append(f"ID {file_id}: {str(e)}")

    return JsonResponse({
        'success': True,
        'deleted_count': deleted_count,
        'permission_denied': len(permission_denied),
        'errors': error_files,
    })


@login_required
@require_http_methods(["POST"])
def download_selected_files(request):
    """Faz download de múltiplos arquivos como ZIP."""
    import zipfile
    import io

    ids = request.POST.getlist('selected_files')
    if not ids:
        return JsonResponse({'error': 'Nenhum arquivo selecionado.'}, status=400)

    files = File.objects.filter(id__in=ids, user=request.user)
    if not files.exists():
        return JsonResponse({'error': 'Nenhum arquivo encontrado.'}, status=404)

    buffer = io.BytesIO()
    seen_names = {}

    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in files:
            if not f.file:
                continue
            try:
                file_path = f.file.path
                if not os.path.isfile(file_path):
                    continue
                # Evita nomes duplicados dentro do ZIP
                base_name = f.name or os.path.basename(file_path)
                if base_name in seen_names:
                    seen_names[base_name] += 1
                    name, ext = os.path.splitext(base_name)
                    arc_name = f"{name}_{seen_names[base_name]}{ext}"
                else:
                    seen_names[base_name] = 0
                    arc_name = base_name
                zf.write(file_path, arc_name)
            except Exception:
                continue

    buffer.seek(0)
    response = HttpResponse(buffer, content_type='application/zip')
    response['Content-Disposition'] = 'attachment; filename="arquivos_selecionados.zip"'
    return response


def handle_chunked_upload(request):
    """Processa upload em chunks"""
    file_chunk = request.FILES.get('file')
    chunk_index = int(request.POST.get('chunkIndex', 0))
    total_chunks = int(request.POST.get('totalChunks', 1))
    file_name = request.POST.get('fileName')
    file_size = int(request.POST.get('fileSize', 0))
    upload_id = request.POST.get('uploadId')
    folder_id = request.POST.get('folder', '')
    
    if not file_chunk or not file_name:
        return JsonResponse({'error': 'Dados de upload inválidos'}, status=400)
    
    if chunk_index == 0:
        user_storage = UserStorage.objects.filter(user=request.user).first()
        user_files = File.objects.filter(user=request.user)
        used_bytes = sum(f.file.size for f in user_files if f.file and os.path.isfile(f.file.path))
        limit_bytes = user_storage.get_storage_limit_bytes() if user_storage else 15 * 1024**3
        
        if used_bytes + file_size > limit_bytes:
            return JsonResponse({
                'error': f'Limite de armazenamento atingido! Você já usou {used_bytes // (1024**2)} MB de {limit_bytes // (1024**2)} MB.'
            }, status=400)
    
    temp_dir = os.path.join(settings.MEDIA_ROOT, 'temp_uploads', str(request.user.id), upload_id)
    os.makedirs(temp_dir, exist_ok=True)
    
    chunk_path = os.path.join(temp_dir, f'{chunk_index}.part')
    with open(chunk_path, 'wb') as f:
        for chunk in file_chunk.chunks():
            f.write(chunk)
    
    if chunk_index == total_chunks - 1:
        return combine_chunks_and_save(request, temp_dir, file_name, folder_id, file_size)
    
    return JsonResponse({
        'success': True,
        'chunkIndex': chunk_index,
        'message': f'Chunk {chunk_index + 1} de {total_chunks} recebido'
    })




def combine_chunks_and_save(request, temp_dir, file_name, folder_id, file_size):
    """Combina todos os chunks e salva o arquivo final"""
    client_hash = request.POST.get('fileHash', '')
    try:
        chunk_files = sorted(
            [f for f in os.listdir(temp_dir) if f.endswith('.part')],
            key=lambda x: int(x.split('.')[0])
        )

        expected_chunks = len(chunk_files)
        if expected_chunks == 0:
            raise ValueError('Nenhum chunk encontrado')

        final_path = os.path.join(temp_dir, file_name)

        with open(final_path, 'wb') as output_file:
            for chunk_file in chunk_files:
                chunk_path = os.path.join(temp_dir, chunk_file)
                with open(chunk_path, 'rb') as input_file:
                    output_file.write(input_file.read())
                os.remove(chunk_path)

        sha256 = hashlib.sha256()
        with open(final_path, 'rb') as f:
            for block in iter(lambda: f.read(65536), b''):
                sha256.update(block)
        server_hash = sha256.hexdigest()

        if client_hash and server_hash != client_hash:
            os.remove(final_path)
            import shutil
            shutil.rmtree(os.path.dirname(temp_dir), ignore_errors=True)
            return JsonResponse({
                'error': f'Falha na verificação de integridade do arquivo "{file_name}". O arquivo foi corrompido durante o envio.',
                'error_type': 'HASH_MISMATCH',
                'server_hash': server_hash,
            }, status=422)
        
        selected_folder = None
        if folder_id:
            selected_folder = Folder.objects.filter(id=folder_id, user=request.user).first()
        
        # Captura a opção is_global do formulário
        is_global = request.POST.get('is_global') == 'true'
        
        new_file = File(user=request.user, name=file_name, is_global=is_global)
        
        if selected_folder:
            new_file.folder = selected_folder.name
        
        with open(final_path, 'rb') as f:
            new_file.file.save(file_name, DjangoFile(f))
        
        file_extension = os.path.splitext(file_name)[1].lower()
        if file_extension in ['.mp4', '.webm', '.mov', '.m4v', '.3gp']:
            try:
                video_path = new_file.file.path
                thumbnail_path = generate_video_thumbnail(video_path)
                if os.path.exists(thumbnail_path):
                    with open(thumbnail_path, 'rb') as thumb_file:
                        django_file = DjangoFile(thumb_file)
                        thumb_name = os.path.splitext(file_name)[0] + '.jpg'
                        new_file.thumbnail.save(thumb_name, django_file, save=True)
                    os.remove(thumbnail_path)
            except Exception as e:
                print(f"Erro ao gerar thumbnail: {e}")
        elif file_extension in ['.heic', '.heif']:
            try:
                heif_path = new_file.file.path
                thumbnail_path = generate_heif_thumbnail(heif_path)
                if thumbnail_path and os.path.exists(thumbnail_path):
                    with open(thumbnail_path, 'rb') as thumb_file:
                        django_file = DjangoFile(thumb_file)
                        thumb_name = os.path.splitext(file_name)[0] + '.jpg'
                        new_file.thumbnail.save(thumb_name, django_file, save=True)
                    os.remove(thumbnail_path)
            except Exception as e:
                print(f"Erro ao gerar thumbnail HEIF: {e}")

        import shutil
        shutil.rmtree(os.path.dirname(temp_dir))
        
        return JsonResponse({
            'success': True,
            'message': 'Arquivo salvo com sucesso!',
            'file_id': new_file.id,
            'is_global': is_global,
            'server_hash': server_hash,
        })

    except Exception as e:
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(os.path.dirname(temp_dir))
        return JsonResponse({'error': f'Erro ao combinar arquivo: {str(e)}'}, status=500)



def handle_normal_upload(request):
    """Upload normal para arquivos pequenos - CORRIGIDA"""
    try:
        files = request.FILES.getlist('file')
        folder_id = request.POST.get('folder', '')
        is_global = request.POST.get('is_global') == 'true'
        client_hash = request.POST.get('fileHash', '')
        
        if not files:
            return JsonResponse({'error': 'Nenhum arquivo selecionado'}, status=400)
        
        selected_folder = None
        if folder_id:
            selected_folder = Folder.objects.filter(id=folder_id, user=request.user).first()
        
        user_storage = UserStorage.objects.filter(user=request.user).first()
        user_files = File.objects.filter(user=request.user)
        
        # Calcular uso atual de armazenamento
        used_bytes = 0
        for f in user_files:
            if f.file and os.path.isfile(f.file.path):
                try:
                    used_bytes += f.file.size
                except (OSError, ValueError):
                    continue
        
        limit_bytes = user_storage.get_storage_limit_bytes() if user_storage else 15 * 1024**3
        
        # Verificar limite de armazenamento
        total_upload_size = sum(f.size for f in files)
        if used_bytes + total_upload_size > limit_bytes:
            return JsonResponse({
                'error': f'Limite de armazenamento atingido! Você já usou {used_bytes // (1024**2)} MB de {limit_bytes // (1024**2)} MB.'
            }, status=400)
        
        saved_files = []
        for uploaded_file in files:
            try:
                mime_ok, mime_type = validate_file_mime(uploaded_file)
                if not mime_ok:
                    return JsonResponse({
                        'error': f'Arquivo bloqueado: tipo "{mime_type}" não é permitido.'
                    }, status=400)

                new_file = File(
                    user=request.user,
                    name=uploaded_file.name,
                    is_global=is_global
                )
                
                if selected_folder:
                    new_file.folder = selected_folder.name
                
                new_file.file.save(uploaded_file.name, uploaded_file)
                
                # Gerar thumbnail para vídeos e imagens iPhone
                file_extension = os.path.splitext(uploaded_file.name)[1].lower()
                if file_extension in ['.mp4', '.webm', '.mov', '.m4v', '.3gp']:
                    try:
                        video_path = new_file.file.path
                        thumbnail_path = generate_video_thumbnail(video_path)
                        if os.path.exists(thumbnail_path):
                            with open(thumbnail_path, 'rb') as f:
                                django_file = DjangoFile(f)
                                thumb_name = os.path.splitext(uploaded_file.name)[0] + '.jpg'
                                new_file.thumbnail.save(thumb_name, django_file, save=True)
                            os.remove(thumbnail_path)
                    except Exception as e:
                        print(f"Erro ao gerar thumbnail: {e}")
                elif file_extension in ['.heic', '.heif']:
                    try:
                        heif_path = new_file.file.path
                        thumbnail_path = generate_heif_thumbnail(heif_path)
                        if thumbnail_path and os.path.exists(thumbnail_path):
                            with open(thumbnail_path, 'rb') as f:
                                django_file = DjangoFile(f)
                                thumb_name = os.path.splitext(uploaded_file.name)[0] + '.jpg'
                                new_file.thumbnail.save(thumb_name, django_file, save=True)
                            os.remove(thumbnail_path)
                    except Exception as e:
                        print(f"Erro ao gerar thumbnail HEIF: {e}")
                
                sha256 = hashlib.sha256()
                with open(new_file.file.path, 'rb') as f:
                    for block in iter(lambda: f.read(65536), b''):
                        sha256.update(block)
                server_hash = sha256.hexdigest()

                if client_hash and server_hash != client_hash:
                    new_file.file.delete(save=False)
                    new_file.delete()
                    return JsonResponse({
                        'error': f'Falha na verificação de integridade do arquivo "{uploaded_file.name}". O arquivo foi corrompido durante o envio.',
                        'error_type': 'HASH_MISMATCH',
                        'server_hash': server_hash,
                    }, status=422)

                saved_files.append({
                    'name': new_file.name,
                    'size': uploaded_file.size,
                    'is_global': is_global,
                    'server_hash': server_hash,
                })

            except Exception as e:
                return JsonResponse({
                    'error': f'Erro ao salvar arquivo {uploaded_file.name}: {str(e)}'
                }, status=500)

        return JsonResponse({
            'success': True,
            'message': f'{len(saved_files)} arquivo(s) enviado(s) com sucesso!',
            'saved_files': saved_files,
            'is_global': is_global,
            'server_hash': saved_files[-1]['server_hash'] if saved_files else '',
        })
        
    except Exception as e:
        return JsonResponse({'error': f'Erro no upload: {str(e)}'}, status=500)



@login_required
def upload_file_chunked(request):
    """View para upload em partes (chunks) - substitui a upload_file original para grandes arquivos"""
    if request.method == 'POST':
        try:
            chunk_index = request.POST.get('chunkIndex')
            
            if chunk_index is not None:
                return handle_chunked_upload(request)
            else:
                return handle_normal_upload(request)
                
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=500)
    
    # Para GET requests, mostrar o formulário de upload
    folders = Folder.objects.filter(user=request.user)
    form = FileForm()  # Use o form atualizado
    return render(request, 'upload_file.html', {'form': form, 'folders': folders})



@login_required 
def upload_file(request):
    return upload_file_chunked(request)

# ============================================================
# GERENCIAMENTO DE NOTAS
# ============================================================

@login_required
def notes_list(request):
    folders = Folder.objects.filter(user=request.user)
    
    folder_id = request.GET.get('folder')
    query = request.GET.get('q', '').strip()
    
    # NOTAS PRÓPRIAS
    user_notes = Note.objects.filter(user=request.user)
    
    # Notas compartilhadas com este usuário (SharedResource)
    shared_notes_ids = SharedResource.objects.filter(
        resource_type='note',
        shared_with=request.user
    ).values_list('resource_id', flat=True)
    
    # Notas compartilhadas publicamente (SharedResource)
    public_notes_ids = SharedResource.objects.filter(
        resource_type='note',
        shared_with_all=True
    ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
    
    # Notas globais (is_global=True)
    global_notes = Note.objects.filter(is_global=True).exclude(user=request.user)
    
    all_shared_ids = list(shared_notes_ids) + list(public_notes_ids)
    shared_notes = Note.objects.filter(id__in=all_shared_ids) if all_shared_ids else Note.objects.none()
    
    # COMBINAR: próprias + compartilhadas + globais
    all_notes = (user_notes | shared_notes | global_notes).distinct()
    
    # Filtros
    if query:
        all_notes = all_notes.filter(
            Q(title__icontains=query) | Q(content__icontains=query) | Q(tags__icontains=query)
        )
    
    selected_folder = None
    subfolders = Folder.objects.none()
    
    if folder_id:
        selected_folder = get_object_or_404(Folder, id=folder_id, user=request.user)
        notes = all_notes.filter(folder=selected_folder)
        subfolders = Folder.objects.filter(user=request.user, parent=selected_folder)
    else:
        notes = all_notes.filter(folder__isnull=True)
        subfolders = Folder.objects.filter(user=request.user, parent__isnull=True)

    return render(request, 'notes_list.html', {
        'folders': folders,
        'notes': notes,
        'selected_folder': selected_folder,
        'subfolders': subfolders,
        'query': query,
        'user_notes_count': user_notes.count(),
        'shared_notes_count': shared_notes.count() + global_notes.count()
    })

@login_required
def delete_notes(request):
    if request.method == 'POST':
        note_ids = request.POST.getlist('selected_notes')
        notes = Note.objects.filter(user=request.user, id__in=note_ids)
        
        deleted_count = 0
        for note in notes:
            note.delete()
            deleted_count += 1
        
        messages.success(request, f"{deleted_count} nota(s) excluída(s) com sucesso!")
    
    return redirect('notes_list')

@login_required
def move_notes_to_folder(request):
    if request.method == 'POST':
        note_ids = request.POST.get('note_ids', '').split(',')
        folder_id = request.POST.get('folder_id')
        
        folder = None
        if folder_id:
            folder = get_object_or_404(Folder, id=folder_id, user=request.user)
        
        moved_count = 0
        for note_id in note_ids:
            try:
                note = Note.objects.get(id=note_id, user=request.user)
                note.folder = folder
                note.save()
                moved_count += 1
            except Note.DoesNotExist:
                continue
        
        messages.success(request, f"{moved_count} nota(s) movida(s) com sucesso!")
    
    return redirect('notes_list')

# RENOMEIE ESTA VIEW PARA EVITAR CONFLITO
@login_required
def move_single_note_to_folder(request):
    if request.method == 'POST':
        note_id = request.POST.get('note_id')
        folder_id = request.POST.get('folder_id')
        note = get_object_or_404(Note, pk=note_id, user=request.user)
        folder = get_object_or_404(Folder, pk=folder_id, user=request.user)

        note.folder = folder
        note.save()
        messages.success(request, "Nota movida com sucesso!")
    return redirect('notes_list')

@login_required
@require_http_methods(["POST"])
def import_txt_notes(request):
    """Importa arquivos .txt como notas."""
    files = request.FILES.getlist('txt_files')
    folder_id = request.POST.get('folder_id') or None

    if not files:
        return JsonResponse({'error': 'Nenhum arquivo enviado.'}, status=400)

    folder = None
    if folder_id:
        folder = get_object_or_404(Folder, id=folder_id, user=request.user)

    created, skipped = [], []
    for f in files:
        if not f.name.lower().endswith('.txt'):
            skipped.append(f.name)
            continue
        try:
            raw = f.read()
            try:
                content = raw.decode('utf-8')
            except UnicodeDecodeError:
                content = raw.decode('latin-1', errors='replace')
            title = os.path.splitext(f.name)[0][:255]
            Note.objects.create(
                title=title,
                content=content,
                user=request.user,
                folder=folder,
            )
            created.append(title)
        except Exception as e:
            skipped.append(f'{f.name}: {e}')

    return JsonResponse({'created': created, 'skipped': skipped})


@login_required
def manage_note(request, pk=None):
    note = get_object_or_404(Note, pk=pk, user=request.user) if pk else None
    form = NoteForm(request.POST or None, instance=note)

    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        obj.save()

        uploaded_file = request.FILES.get('file_upload')
        if uploaded_file:
            new_file = File(user=request.user, name=uploaded_file.name)
            new_file.file.save(uploaded_file.name, uploaded_file)
            new_file.save()

        messages.success(request, "Nota salva com sucesso!")
        return redirect('notes_list')

    return render(request, 'form.html', {
        'form': form,
        'title': 'Editar Nota' if note else 'Adicionar Nota',
        'show_file_input': True,
    })

@login_required
def delete_note(request, pk):
    note = get_object_or_404(Note, pk=pk, user=request.user)
    note.delete()
    messages.success(request, "Nota excluída com sucesso!")
    return redirect('notes_list')

@login_required
def download_notes(request):
    notes = Note.objects.filter(user=request.user)
    content = "\n\n".join([f"{n.title}\n{n.content}" for n in notes])
    response = HttpResponse(content, content_type='text/plain')
    response['Content-Disposition'] = 'attachment; filename=notas.txt'
    return response

@login_required
def download_single_note(request, pk):
    note = get_object_or_404(Note, pk=pk, user=request.user)
    content = f"{note.title}\n\n{note.content}"
    response = HttpResponse(content, content_type='text/plain')
    response['Content-Disposition'] = f'attachment; filename="{note.title}.txt"'
    return response

@login_required
def manage_folder(request, pk=None):
    folder = get_object_or_404(Folder, pk=pk, user=request.user) if pk else None
    form = FolderForm(request.POST or None, instance=folder)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        obj.save()
        messages.success(request, "Pasta salva com sucesso!")
        return redirect('notes_list')
    return render(request, 'form.html', {'form': form, 'title': 'Editar Pasta' if folder else 'Adicionar Pasta'})
    
# ============================================================
# GERENCIAMENTO DE DORKS
# ============================================================

@login_required
def dork_list(request):
    # Dorks próprios
    user_dorks = Dork.objects.filter(user=request.user)
    
    # Dorks compartilhados com este usuário (SharedResource)
    shared_dorks_ids = SharedResource.objects.filter(
        resource_type='dork',
        shared_with=request.user
    ).values_list('resource_id', flat=True)
    
    # Dorks compartilhados publicamente (SharedResource)
    public_dorks_ids = SharedResource.objects.filter(
        resource_type='dork',
        shared_with_all=True
    ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
    
    # Dorks globais (is_global=True)
    global_dorks = Dork.objects.filter(is_global=True).exclude(user=request.user)
    
    all_shared_ids = list(shared_dorks_ids) + list(public_dorks_ids)
    shared_dorks = Dork.objects.filter(id__in=all_shared_ids) if all_shared_ids else Dork.objects.none()
    
    # Combinar: próprios + compartilhados + globais
    all_dorks = (user_dorks | shared_dorks | global_dorks).distinct().order_by('platform')
    
    return render(request, 'dork_list.html', {
        'dorks': all_dorks,
        'user_dorks_count': user_dorks.count(),
        'shared_dorks_count': shared_dorks.count() + global_dorks.count()
    })

@login_required
def manage_dork(request, pk=None):
    dork = get_object_or_404(Dork, pk=pk, user=request.user) if pk else None
    form = DorkForm(request.POST or None, instance=dork)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        obj.save()
        messages.success(request, "Dork salvo com sucesso!")
        return redirect('dork_list')
    return render(request, 'form.html', {'form': form, 'title': 'Editar Dork' if dork else 'Adicionar Dork'})

@login_required
def delete_dork(request, pk):
    dork = get_object_or_404(Dork, pk=pk, user=request.user)
    dork.delete()
    messages.success(request, "Dork excluído com sucesso!")
    return redirect('dork_list')

@login_required
def add_dork_note(request, dork_pk):
    dork = get_object_or_404(Dork, pk=dork_pk, user=request.user)
    form = DorkNoteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        obj.dork = dork
        obj.save()
        messages.success(request, "Nota adicionada ao dork com sucesso!")
        return redirect('dork_list')
    return render(request, 'form.html', {'form': form, 'title': f'Adicionar Nota para Dork [{dork.query}]'})

@login_required
def dork_search(request):
    platforms = ['DuckDuckGo', 'Shodan', 'Wigle.net']
    dorks = Dork.objects.filter(user=request.user)
    selected_platform = request.GET.get('platform')
    selected_dork_id = request.GET.get('dork')
    argument = request.GET.get('argument')

    if request.method == 'GET' and selected_platform and selected_dork_id and argument:
        dork = Dork.objects.get(pk=selected_dork_id, user=request.user)
        if selected_platform == 'DuckDuckGo':
            url = f"https://duckduckgo.com/?q={dork.query.replace('{ARG}', argument)}"
        elif selected_platform == 'Shodan':
            url = f"https://www.shodan.io/search?query={dork.query.replace('{ARG}', argument)}"
        elif selected_platform == 'Wigle.net':
            url = f"https://wigle.net/search?query={dork.query.replace('{ARG}', argument)}"
        else:
            url = "#"
        return redirect(url)

    return render(request, 'dork_search.html', {
        'platforms': platforms,
        'dorks': dorks,
    })

@login_required
def import_dorks(request):
    if request.method == 'POST':
        form = DorkImportForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data['file']
            is_global = form.cleaned_data.get('is_global', False)  # Nova opção
            decoded_file = file.read().decode('utf-8').splitlines()
            reader = csv.DictReader(decoded_file)
            count = 0
            for row in reader:
                Dork.objects.create(
                    query=row.get('query', ''),
                    description=row.get('description', ''),
                    platform=row.get('platform', ''),
                    user=request.user,
                    is_global=is_global  # Define se é global
                )
                count += 1
            messages.success(request, f'{count} dorks importadas com sucesso!')
            return redirect('dork_list')
    else:
        form = DorkImportForm()
    return render(request, 'import_dorks.html', {'form': form})

# ============================================================
# GERENCIAMENTO DE FERRAMENTAS
# ============================================================

@login_required
def tool_list(request):
    query = request.GET.get('q', '').strip()
    selected_category = request.GET.get('category', '')
    
    # Ferramentas próprias
    user_tools = Tool.objects.filter(user=request.user)
    
    # Ferramentas compartilhadas com este usuário (SharedResource)
    shared_tools_ids = SharedResource.objects.filter(
        resource_type='tool',
        shared_with=request.user
    ).values_list('resource_id', flat=True)
    
    # Ferramentas compartilhadas publicamente (SharedResource)
    public_tools_ids = SharedResource.objects.filter(
        resource_type='tool',
        shared_with_all=True
    ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
    
    # Ferramentas globais (is_global=True)
    global_tools = Tool.objects.filter(is_global=True).exclude(user=request.user)
    
    all_shared_ids = list(shared_tools_ids) + list(public_tools_ids)
    shared_tools = Tool.objects.filter(id__in=all_shared_ids) if all_shared_ids else Tool.objects.none()
    
    # Combinar: próprias + compartilhadas + globais
    tools = (user_tools | shared_tools | global_tools).distinct()
    
    if query:
        tools = tools.filter(
            Q(name__icontains=query) |
            Q(category__icontains=query) |
            Q(description__icontains=query))
    
    if selected_category:
        tools = tools.filter(category=selected_category)
    
    tools = tools.order_by('category', 'name')
    
    paginator = Paginator(tools, 10)
    page_number = request.GET.get('page')
    tools_page = paginator.get_page(page_number)
    
    tools_by_category = {}
    for tool in tools:
        cat = tool.category or 'Outros'
        tools_by_category.setdefault(cat, []).append(tool)
    
    all_categories = tools.values_list('category', flat=True).distinct()
    
    if request.method == 'POST':
        form = ToolImportForm(request.POST, request.FILES)
        
        if form.is_valid():
            file = form.cleaned_data['file']
            
            try:
                if file.name.endswith('.json'):
                    data = json.load(file)
                    for item in data:
                        Tool.objects.create(
                            name=item.get('name', ''),
                            category=item.get('category', ''),
                            description=item.get('description', ''),
                            homepage=item.get('homepage', ''),
                            user=request.user
                        )
                
                elif file.name.endswith('.csv'):
                    decoded_file = file.read().decode('utf-8').splitlines()
                    reader = csv.DictReader(decoded_file)
                    for row in reader:
                        Tool.objects.create(
                            name=row.get('name', ''),
                            category=row.get('category', ''),
                            description=row.get('description', ''),
                            homepage=row.get('homepage', ''),
                            user=request.user
                        )
                
                else:
                    messages.error(request, 'Formato de arquivo não suportado. Use JSON ou CSV.')
                    return redirect('tool_list')
                
                messages.success(request, 'Ferramentas importadas com sucesso!')
                return redirect('tool_list')
                
            except Exception as e:
                messages.error(request, f'Erro ao processar arquivo: {e}')
                return redirect('tool_list')
    else:
        form = ToolImportForm()
    
    return render(request, 'tool_list.html', {
        'tools': tools_page,
        'tools_by_category': tools_by_category,
        'form': form,
        'query': query,
        'all_categories': all_categories,
        'selected_category': selected_category,
        'user_tools_count': user_tools.count(),
        'shared_tools_count': shared_tools.count() + global_tools.count()
    })


@login_required
def manage_tool(request, pk=None):
    tool = get_object_or_404(Tool, pk=pk, user=request.user) if pk else None
    form = ToolForm(request.POST or None, instance=tool)
    
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        obj.save()
        messages.success(request, "Ferramenta salva com sucesso!")
        return redirect('tool_list')
    
    return render(request, 'form.html', {
        'form': form,
        'title': 'Editar Ferramenta' if tool else 'Adicionar Ferramenta'
    })

@login_required
def delete_tool(request, pk):
    tool = get_object_or_404(Tool, pk=pk, user=request.user)
    tool.delete()
    messages.success(request, "Ferramenta excluída com sucesso!")
    return redirect('tool_list')

@login_required
def add_tool_note(request, tool_pk):
    tool = get_object_or_404(Tool, pk=tool_pk, user=request.user)
    form = ToolNoteForm(request.POST or None)
    
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        obj.tool = tool
        obj.save()
        messages.success(request, "Nota adicionada à ferramenta com sucesso!")
        return redirect('tool_list')
    
    return render(request, 'form.html', {
        'form': form,
        'title': f'Adicionar Nota para {tool.name}'
    })


@login_required
def import_tools(request):
    if request.method == 'POST':
        form = ToolImportForm(request.POST, request.FILES)
        if form.is_valid():
            file = form.cleaned_data['file']
            is_global = form.cleaned_data.get('is_global', False)  # Nova opção
            count = 0
            
            if file.name.endswith('.csv'):
                decoded_file = file.read().decode('utf-8').splitlines()
                reader = csv.DictReader(decoded_file)
                for row in reader:
                    description = row.get('description') or row.get('description') or ''
                    tool, created = Tool.objects.get_or_create(
                        name=row.get('name', ''),
                        defaults={
                            'category': row.get('category', ''),
                            'description': description,
                            'homepage': row.get('homepage', ''),
                            'user': request.user,
                            'is_global': is_global  # Define se é global
                        }
                    )
                    if created:
                        count += 1
            
            elif file.name.endswith('.json'):
                data = json.load(file)
                for item in data:
                    description = item.get('description') or item.get('description') or ''
                    tool, created = Tool.objects.get_or_create(
                        name=item.get('name', ''),
                        defaults={
                            'category': item.get('category', ''),
                            'description': description,
                            'homepage': item.get('homepage', ''),
                            'user': request.user,
                            'is_global': is_global  # Define se é global
                        }
                    )
                    if created:
                        count += 1
            
            else:
                messages.error(request, 'Formato de arquivo não suportado.')
                return redirect('tool_list')
            
            messages.success(request, f'{count} ferramentas importadas com sucesso.')
            return redirect('tool_list')
    
    else:
        form = ToolImportForm()
    return render(request, 'import_tools.html', {'form': form})

# ============================================================
# GERENCIAMENTO DE CVEs
# ============================================================

def fetch_latest_cves(limit=20):
    url = 'https://services.nvd.nist.gov/rest/json/cves/2.0'
    params = {'resultsPerPage': limit, 'startIndex': 0}
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        cve_list = []
        for item in data.get("vulnerabilities", []):
            cve_data = item.get("cve", {})
            descriptions = cve_data.get("descriptions", [])
            description = ""
            for desc in descriptions:
                if desc.get("lang") == "en":
                    description = desc.get("value", "")
                    break
            if not description and descriptions:
                description = descriptions[0].get("value", "")

            metrics = cve_data.get("metrics", {})
            severity = "N/A"
            if "cvssMetricV31" in metrics:
                severity = metrics["cvssMetricV31"][0].get("cvssData", {}).get("baseSeverity", "N/A")
            elif "cvssMetricV30" in metrics:
                severity = metrics["cvssMetricV30"][0].get("cvssData", {}).get("baseSeverity", "N/A")

            # Processar data para o template
            published = cve_data.get("published", "")
            published_date = ""
            if published and 'T' in published:
                published_date = published.split('T')[0]

            cve_list.append({
                'cve_id': cve_data.get("id"),
                'description': description,
                'severity': severity,
                'published_date': published_date,  # Agora só a data
                'link': f"https://nvd.nist.gov/vuln/detail/{cve_data.get('id')}",
            })
        return cve_list
    except Exception as e:
        print("Erro ao buscar CVEs:", e)
        return []


@login_required
def cve_list(request):
    year_filter = request.GET.get('year')
    search = request.GET.get('search', '')
    start_date = request.GET.get('start')
    end_date = request.GET.get('end')

    # Consulta otimizada usando apenas o ORM
    user_cves = CVE.objects.filter(user=request.user).select_related('user')
    global_cves = CVE.objects.filter(is_global=True).exclude(user=request.user).select_related('user')
    
    # Combinação usando | (or) em vez de union para manter o QuerySet
    all_cves = user_cves | global_cves

    # Aplicar filtros diretamente no ORM
    if year_filter and year_filter.isdigit():
        all_cves = all_cves.filter(cve_id__startswith=f'CVE-{year_filter}-')
    
    if search:
        all_cves = all_cves.filter(
            models.Q(cve_id__icontains=search) |
            models.Q(description__icontains=search) |
            models.Q(severity__icontains=search)
        )
    
    if start_date:
        all_cves = all_cves.filter(published_date__gte=start_date)
    
    if end_date:
        all_cves = all_cves.filter(published_date__lte=end_date)

    # Ordenação para melhor performance
    all_cves = all_cves.order_by('-published_date').distinct()

    # Paginação ANTES de processar os dados
    paginator = Paginator(all_cves, 20)
    page = request.GET.get('page')
    cves_page = paginator.get_page(page)

    # Buscar CVEs públicas apenas se necessário (primeira página)
    public_cves = []
    if cves_page.number == 1 and not any([year_filter, search, start_date, end_date]):
        public_cves = fetch_latest_cves()

    # Processar apenas os dados da página atual
    user_cves_list = [
        {
            'cve_id': cve.cve_id,
            'description': cve.description,
            'severity': cve.severity,
            'published_date': cve.published_date,
            'link': cve.references,
            'is_global': cve.is_global,
            'user': cve.user.username if cve.user else 'Sistema'
        }
        for cve in cves_page
    ]

    # Combinar apenas se necessário
    all_cves_combined = user_cves_list + public_cves

    # Correção: Obter anos disponíveis de forma otimizada
    try:
        # Método 1: Usando dates (mais eficiente)
        years_dates = CVE.objects.dates('published_date', 'year')
        cve_years = sorted([str(date.year) for date in years_dates], reverse=True)
    except:
        # Método 2: Fallback - extrair anos dos CVE IDs
        cve_ids = CVE.objects.values_list('cve_id', flat=True)
        years = set()
        for cve_id in cve_ids:
            if cve_id and cve_id.startswith('CVE-'):
                parts = cve_id.split('-')
                if len(parts) >= 2 and parts[1].isdigit():
                    years.add(parts[1])
        cve_years = sorted(years, reverse=True)

    return render(request, 'cve_list.html', {
        'cves_page': cves_page,
        'cve_years': cve_years,
        'selected_year': year_filter or '',
        'all_cves_combined': all_cves_combined,
    })


@login_required
def add_cve(request):
    form = CVEForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        obj.save()
        messages.success(request, "CVE salva com sucesso!")
        return redirect('cve_list')
    return render(request, 'form.html', {'form': form, 'title': 'Adicionar CVE'})


# views.py - Atualize a view import_cves
@login_required
def import_cves(request):
    if request.method == 'POST':
        form = CVEUploadForm(request.POST, request.FILES)
        if form.is_valid():
            files = request.FILES.getlist('files')  # Agora usa getlist
            
            if not files:
                messages.error(request, "Nenhum arquivo selecionado.")
                return redirect('import_cves')
            
            success_count = 0
            error_files = []
            
            for file in files:
                try:
                    filename = file.name
                    
                    if filename.endswith('.json'):
                        data = json.load(file)
                        vulnerabilities = data.get("vulnerabilities", [])
                        
                        if not vulnerabilities:
                            error_files.append(f"{filename}: Sem chave 'vulnerabilities'")
                            continue
                        
                        cves_imported = process_json_vulnerabilities(vulnerabilities, request.user)
                        success_count += cves_imported
                        
                    elif filename.endswith('.csv'):
                        cves_imported = process_csv_file(file, request.user)
                        success_count += cves_imported
                        
                    else:
                        error_files.append(f"{filename}: Formato não suportado")
                        continue
                        
                except Exception as e:
                    error_files.append(f"{filename}: {str(e)}")
                    continue
            
            if success_count > 0:
                messages.success(request, f'✅ {success_count} CVEs importados com sucesso de {len(files)} arquivo(s)!')
            if error_files:
                messages.warning(request, f'⚠️ Erros em {len(error_files)} arquivo(s): ' + ' | '.join(error_files))
            
            return redirect('cve_list')
    
    else:
        form = CVEUploadForm()
    
    return render(request, 'import_cves.html', {'form': form})


def process_json_vulnerabilities(vulnerabilities, user):
    cves_imported = 0
    
    for item in vulnerabilities:
        try:
            cve_data = item.get("cve", {})
            cve_id = cve_data.get("id")
            
            if not cve_id:
                continue
            
            # Verificar se já existe
            if CVE.objects.filter(cve_id=cve_id).exists():
                continue
            
            descriptions = cve_data.get("descriptions", [])
            description = next((d.get("value") for d in descriptions if d.get("lang") == "en"), "")
            
            severity = "N/A"
            metrics = cve_data.get("metrics", {})
            if "cvssMetricV31" in metrics:
                severity = metrics["cvssMetricV31"][0].get("cvssData", {}).get("baseSeverity", "N/A")
            elif "cvssMetricV30" in metrics:
                severity = metrics["cvssMetricV30"][0].get("cvssData", {}).get("baseSeverity", "N/A")
            elif "cvssMetricV2" in metrics:
                severity = metrics["cvssMetricV2"][0].get("baseSeverity", "N/A")
            
            references = cve_data.get("references", [])
            link = references[0]["url"] if references else f"https://nvd.nist.gov/vuln/detail/{cve_id}"
            
            # CORREÇÃO PRINCIPAL: Processar data corretamente
            published = cve_data.get("published", "")
            published_date = None
            
            if published:
                try:
                    # Extrair apenas a parte da data (YYYY-MM-DD) antes do 'T'
                    if 'T' in published:
                        date_only = published.split('T')[0]
                        published_date = datetime.strptime(date_only, '%Y-%m-%d').date()
                    else:
                        # Se não tiver 'T', tentar parse direto
                        published_date = datetime.strptime(published, '%Y-%m-%d').date()
                except (ValueError, IndexError) as e:
                    print(f"Erro ao processar data {published}: {e}")
                    # Usar data atual como fallback
                    published_date = timezone.now().date()
            else:
                # Se não houver data, usar data atual
                published_date = timezone.now().date()
            
            # Criar CVE
            CVE.objects.create(
                cve_id=cve_id,
                description=description,
                severity=severity,
                references=link,
                published_date=published_date,
                user=user
            )
            cves_imported += 1
            
        except Exception as e:
            print(f"Erro ao processar CVE {cve_id}: {e}")
            continue
    
    return cves_imported


def process_csv_file(file, user):
    cves_imported = 0
    
    decoded = file.read().decode('utf-8').splitlines()
    reader = csv.DictReader(decoded)
    
    for row in reader:
        obj, created = CVE.objects.get_or_create(
            cve_id=row.get('cve_id'),
            defaults={
                "description": row.get('description', ''),
                "severity": row.get('severity', ''),
                "references": row.get('references', ''),
                "user": user
            }
        )
        
        if created:
            cves_imported += 1
    
    return cves_imported

# ============================================================
# GERENCIAMENTO DE PROJETOS
# ============================================================

@login_required
def project_list(request):
    projects = Project.objects.filter(user=request.user).prefetch_related('projectitem_set')
    return render(request, 'project_list.html', {'projects': projects})

@login_required
def manage_project(request, pk=None):
    project = get_object_or_404(Project, pk=pk, user=request.user) if pk else None
    form = ProjectForm(request.POST or None, instance=project)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.user = request.user
        obj.save()
        messages.success(request, "Projeto salvo com sucesso!")
        return redirect('project_list')
    return render(request, 'form.html', {'form': form, 'title': 'Editar Projeto' if project else 'Adicionar Projeto'})

@login_required
def delete_project(request, pk):
    project = get_object_or_404(Project, pk=pk, user=request.user)
    project.delete()
    messages.success(request, "Projeto excluído com sucesso!")
    return redirect('project_list')

@login_required
def add_project_item(request, project_pk):
    project = get_object_or_404(Project, pk=project_pk, user=request.user)
    form = ProjectItemForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.project = project
        obj.save()
        messages.success(request, "Item adicionado ao projeto com sucesso!")
        return redirect('project_list')
    return render(request, 'form.html', {'form': form, 'title': f'Adicionar Item ao Projeto {project.name}'})

# ============================================================
# LINKS DE RECURSOS
# ============================================================

@login_required
def resource_links_list(request):
    # Links próprios
    user_links = ResourceLink.objects.filter(user=request.user)
    
    # Links compartilhados com este usuário (SharedResource)
    shared_links_ids = SharedResource.objects.filter(
        resource_type='resource_link',
        shared_with=request.user
    ).values_list('resource_id', flat=True)
    
    # Links compartilhados publicamente (SharedResource)
    public_links_ids = SharedResource.objects.filter(
        resource_type='resource_link',
        shared_with_all=True
    ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
    
    # Links globais (is_global=True)
    global_links = ResourceLink.objects.filter(is_global=True).exclude(user=request.user)
    
    all_shared_ids = list(shared_links_ids) + list(public_links_ids)
    shared_links = ResourceLink.objects.filter(id__in=all_shared_ids) if all_shared_ids else ResourceLink.objects.none()
    
    # Combinar: próprios + compartilhados + globais
    all_links = (user_links | shared_links | global_links).distinct()
    
    return render(request, 'resource_links_list.html', {
        'links': all_links,
        'user_links_count': user_links.count(),
        'shared_links_count': shared_links.count() + global_links.count()
    })

@login_required
def add_resource_link(request):
    form = ResourceLinkForm(request.POST or None)
    if form.is_valid():
        link = form.save(commit=False)
        link.user = request.user
        link.save()
        return redirect('resource_links_list')
    return render(request, 'form.html', {'form': form, 'title': 'Adicionar Link de Recurso'})

# ============================================================
# CANAIS DO YOUTUBE
# ============================================================

@login_required
def add_youtube_channel(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        url = request.POST.get('url')
        description = request.POST.get('description', '')

        if name and url:
            YouTubeChannel.objects.create(
                name=name, url=url, description=description, user=request.user
            )
            return redirect('dashboard')

    return render(request, 'add_youtube_channel.html')

@login_required
def youtube_channels_list(request):
    # Canais próprios
    user_channels = YouTubeChannel.objects.filter(user=request.user)
    
    # Canais compartilhados com este usuário (SharedResource)
    shared_channels_ids = SharedResource.objects.filter(
        resource_type='youtube_channel',
        shared_with=request.user
    ).values_list('resource_id', flat=True)
    
    # Canais compartilhados publicamente (SharedResource)
    public_channels_ids = SharedResource.objects.filter(
        resource_type='youtube_channel',
        shared_with_all=True
    ).exclude(shared_by=request.user).values_list('resource_id', flat=True)
    
    # Canais globais (is_global=True)
    global_channels = YouTubeChannel.objects.filter(is_global=True).exclude(user=request.user)
    
    all_shared_ids = list(shared_channels_ids) + list(public_channels_ids)
    shared_channels = YouTubeChannel.objects.filter(id__in=all_shared_ids) if all_shared_ids else YouTubeChannel.objects.none()
    
    # Combinar: próprios + compartilhados + globais
    all_channels = (user_channels | shared_channels | global_channels).distinct()
    
    return render(request, 'youtube_channels_list.html', {
        'channels': all_channels,
        'user_channels_count': user_channels.count(),
        'shared_channels_count': shared_channels.count() + global_channels.count()
    })

# ============================================================
# TERMINAL VIRTUAL E INTERFACE GRÁFICA
# ============================================================

@login_required
def virtual_terminal(request, pk):
    return render(request, 'virtual_terminal.html', {'project_id': pk})

@login_required
def virtual_gui(request, pk):
    remote_url = f"https://guacamole.seuservidor.com/?project={pk}&user={request.user.username}"
    return redirect(remote_url)

# ============================================================
# HANDLER DE ERROS
# ============================================================

def handler404(request, exception=None):
    """
    Handler para erro 404 - Página não encontrada
    """
    print(f"404 Error - Path: {request.path}")
    return render(request, '404.html', status=404)

def handler500(request):
    """
    Handler para erro 500 - Erro interno do servidor
    """
    print("500 Error - Internal Server Error")
    return render(request, '500.html', status=500)


# ========== FUNÇÕES DE COMPARTILHAMENTO ==========

@login_required
def share_resource(request):
    """View para compartilhar recursos"""
    if request.method == 'POST':
        resource_type = request.POST.get('resource_type')
        resource_id = request.POST.get('resource_id')
        shared_with_all = request.POST.get('shared_with_all') == 'true'
        user_ids = request.POST.getlist('users')
        permission = request.POST.get('permission', 'view')
        
        print(f"DEBUG: Sharing {resource_type} ID {resource_id}, public: {shared_with_all}, users: {user_ids}")
        
        # Mapeamento de tipos para modelos
        resource_models = {
            'file': File,
            'note': Note,
            'tool': Tool,
            'dork': Dork,
            'resource_link': ResourceLink,
            'youtube_channel': YouTubeChannel,
        }
        
        if resource_type not in resource_models:
            return JsonResponse({'error': 'Tipo de recurso inválido'}, status=400)
        
        try:
            resource = get_object_or_404(resource_models[resource_type], id=resource_id, user=request.user)
        except Exception as e:
            return JsonResponse({'error': f'Recurso não encontrado ou sem permissão: {str(e)}'}, status=404)
        
        # Criar ou atualizar compartilhamento
        shared_resource, created = SharedResource.objects.get_or_create(
            resource_type=resource_type,
            resource_id=resource_id,
            shared_by=request.user,
            defaults={
                'shared_with_all': shared_with_all,
                'permission': permission
            }
        )
        
        if not created:
            shared_resource.shared_with_all = shared_with_all
            shared_resource.permission = permission
            shared_resource.save()
        
        # Gerenciar usuários específicos
        if not shared_with_all and user_ids:
            users = User.objects.filter(id__in=user_ids)
            shared_resource.shared_with.set(users)
            shared_resource.shared_with_all = False
        elif shared_with_all:
            shared_resource.shared_with.clear()
            shared_resource.shared_with_all = True
        
        shared_resource.save()
        
        print(f"DEBUG: Successfully shared {resource_type} {resource_id}")
        
        return JsonResponse({
            'success': True, 
            'message': f'{resource_type.replace("_", " ").title()} compartilhado com sucesso!'
        })
    
    return JsonResponse({'error': 'Método não permitido'}, status=405)

@login_required
def get_shareable_users(request):
    """View para obter usuários disponíveis para compartilhamento"""
    users = User.objects.exclude(id=request.user.id).values('id', 'username', 'email')
    return JsonResponse({'users': list(users)})

@login_required
def shared_with_me(request):
    """View para recursos compartilhados com o usuário - OTIMIZADA"""
    user = request.user
    
    # Inicializar listas
    shared_files = []
    shared_notes = []
    shared_tools = []
    shared_dorks = []
    shared_links = []
    shared_channels = []
    shared_cves = []

    # SISTEMA 1: Recursos Globais (is_global=True)
    global_files = File.objects.filter(is_global=True).exclude(user=user).select_related('global_created_by', 'user')
    global_notes = Note.objects.filter(is_global=True).exclude(user=user).select_related('global_created_by', 'user')
    global_tools = Tool.objects.filter(is_global=True).exclude(user=user).select_related('global_created_by', 'user')
    global_dorks = Dork.objects.filter(is_global=True).exclude(user=user).select_related('global_created_by', 'user')
    global_links = ResourceLink.objects.filter(is_global=True).exclude(user=user).select_related('global_created_by', 'user')
    global_channels = YouTubeChannel.objects.filter(is_global=True).exclude(user=user).select_related('global_created_by', 'user')
    global_cves = CVE.objects.filter(is_global=True).exclude(user=user).select_related('user')

    # Processar recursos globais
    for file in global_files:
        shared_files.append({
            'resource': file,
            'shared_by': file.global_created_by or file.user,
            'permission': 'view',
            'shared_at': file.uploaded_at,
            'is_global': True
        })

    for note in global_notes:
        shared_notes.append({
            'resource': note,
            'shared_by': note.global_created_by or note.user,
            'permission': 'view',
            'shared_at': note.created_at,
            'is_global': True
        })

    for tool in global_tools:
        shared_tools.append({
            'resource': tool,
            'shared_by': tool.global_created_by or tool.user,
            'permission': 'view',
            'shared_at': tool.created_at,
            'is_global': True
        })

    for dork in global_dorks:
        shared_dorks.append({
            'resource': dork,
            'shared_by': dork.global_created_by or dork.user,
            'permission': 'view',
            'shared_at': dork.created_at,
            'is_global': True
        })

    for link in global_links:
        shared_links.append({
            'resource': link,
            'shared_by': link.global_created_by or link.user,
            'permission': 'view',
            'shared_at': link.created_at,
            'is_global': True
        })

    for channel in global_channels:
        shared_channels.append({
            'resource': channel,
            'shared_by': channel.global_created_by or channel.user,
            'permission': 'view',
            'shared_at': channel.created_at,
            'is_global': True
        })

    for cve in global_cves:
        shared_cves.append({
            'resource': cve,
            'shared_by': cve.user,
            'permission': 'view',
            'shared_at': cve.published_date,
            'is_global': True
        })

    # SISTEMA 2: SharedResources
    specific_shared = SharedResource.objects.filter(shared_with=user).select_related('shared_by')
    public_shared = SharedResource.objects.filter(shared_with_all=True).exclude(shared_by=user).select_related('shared_by')
    all_shared = (specific_shared | public_shared).distinct()

    # Mapeamento de tipos para modelos
    resource_models = {
        'file': File,
        'note': Note,
        'tool': Tool,
        'dork': Dork,
        'resource_link': ResourceLink,
        'youtube_channel': YouTubeChannel,
    }

    # Buscar recursos em lotes para evitar N+1
    resource_ids_by_type = {}
    for shared in all_shared:
        if shared.resource_type not in resource_ids_by_type:
            resource_ids_by_type[shared.resource_type] = []
        resource_ids_by_type[shared.resource_type].append(shared.resource_id)

    resources_cache = {}
    for resource_type, ids in resource_ids_by_type.items():
        if resource_type in resource_models:
            model = resource_models[resource_type]
            resources_cache[resource_type] = {
                obj.id: obj for obj in model.objects.filter(id__in=ids)
            }

    # Processar SharedResources
    for shared in all_shared:
        try:
            if shared.resource_type in resources_cache:
                resource_cache = resources_cache[shared.resource_type]
                resource = resource_cache.get(shared.resource_id)
                
                if resource:
                    shared_data = {
                        'resource': resource,
                        'shared_by': shared.shared_by,
                        'permission': shared.permission,
                        'shared_at': shared.created_at,
                        'is_global': False
                    }
                    
                    if shared.resource_type == 'file':
                        shared_files.append(shared_data)
                    elif shared.resource_type == 'note':
                        shared_notes.append(shared_data)
                    elif shared.resource_type == 'tool':
                        shared_tools.append(shared_data)
                    elif shared.resource_type == 'dork':
                        shared_dorks.append(shared_data)
                    elif shared.resource_type == 'resource_link':
                        shared_links.append(shared_data)
                    elif shared.resource_type == 'youtube_channel':
                        shared_channels.append(shared_data)
                        
        except Exception as e:
            print(f"DEBUG: ERRO ao processar SharedResource {shared.resource_type} ID {shared.resource_id}: {str(e)}")
            # Remove o SharedResource se o recurso original não existir mais
            shared.delete()
            continue

    return render(request, 'shared_with_me.html', {
        'shared_files': shared_files,
        'shared_notes': shared_notes,
        'shared_tools': shared_tools,
        'shared_dorks': shared_dorks,
        'shared_links': shared_links,
        'shared_channels': shared_channels,
        'shared_cves': shared_cves,
    })

# ========== FUNÇÕES DE DEBUG ==========

@login_required
def debug_shared_resources(request):
    """View otimizada para debug do sistema de compartilhamento"""
    # Cache para reduzir carga
    cache_key = f"debug_shared_{request.user.id}_{request.GET.get('page', 1)}"
    cached_data = cache.get(cache_key)
    
    if cached_data and not request.GET.get('refresh'):
        return render(request, 'debug_shared.html', cached_data)
    
    user = request.user
    
    # SISTEMA 1: SharedResource - Consultas otimizadas
    shared_with_user = SharedResource.objects.filter(
        shared_with=user
    ).select_related('shared_by').prefetch_related('shared_with').order_by('-created_at')
    
    shared_public = SharedResource.objects.filter(
        shared_with_all=True
    ).exclude(shared_by=user).select_related('shared_by').order_by('-created_at')
    
    # Contagem por tipo - Consulta única otimizada
    shared_resource_counts = SharedResource.objects.filter(
        Q(shared_with=user) | Q(shared_with_all=True)
    ).exclude(
        shared_by=user, shared_with_all=True
    ).values('resource_type').annotate(
        count=Count('id')
    ).order_by('resource_type')
    
    resource_counts = {item['resource_type']: item['count'] for item in shared_resource_counts}
    
    # SISTEMA 2: Recursos Globais - Apenas contagens para performance
    global_counts_data = {
        'file': File.objects.filter(is_global=True).exclude(user=user).count(),
        'note': Note.objects.filter(is_global=True).exclude(user=user).count(),
        'tool': Tool.objects.filter(is_global=True).exclude(user=user).count(),
        'dork': Dork.objects.filter(is_global=True).exclude(user=user).count(),
        'resource_link': ResourceLink.objects.filter(is_global=True).exclude(user=user).count(),
        'youtube_channel': YouTubeChannel.objects.filter(is_global=True).exclude(user=user).count(),
        'cve': CVE.objects.filter(is_global=True).exclude(user=user).count(),
    }
    
    global_counts = {
        'total': sum(global_counts_data.values()),
        'types': global_counts_data
    }
    
    # Total de usuários
    total_users = User.objects.count()
    
    # Paginação para SharedResources
    all_shared_resources = list(shared_with_user) + list(shared_public)
    paginator = Paginator(all_shared_resources, 25)
    page_number = request.GET.get('page', 1)
    
    try:
        shared_page = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        shared_page = paginator.page(1)
    
    # Carregar recursos globais apenas se solicitado
    load_global_details = request.GET.get('load_global') == 'true'
    global_resources = {}
    
    if load_global_details:
        global_resources = {
            'file': File.objects.filter(is_global=True).exclude(user=user)
                      .select_related('global_created_by', 'user')[:50],
            'note': Note.objects.filter(is_global=True).exclude(user=user)
                      .select_related('global_created_by', 'user')[:50],
            'tool': Tool.objects.filter(is_global=True).exclude(user=user)
                      .select_related('global_created_by', 'user')[:50],
            'dork': Dork.objects.filter(is_global=True).exclude(user=user)
                      .select_related('global_created_by', 'user')[:50],
            'resource_link': ResourceLink.objects.filter(is_global=True).exclude(user=user)
                              .select_related('global_created_by', 'user')[:50],
            'youtube_channel': YouTubeChannel.objects.filter(is_global=True).exclude(user=user)
                                .select_related('global_created_by', 'user')[:50],
            'cve': CVE.objects.filter(is_global=True).exclude(user=user)
                    .select_related('user')[:50],
        }
    
    context = {
        'shared_with_user': shared_with_user,
        'shared_public': shared_public,
        'shared_page': shared_page,
        'resource_counts': resource_counts,
        'global_counts': global_counts,
        'global_resources': global_resources if load_global_details else {},
        'total_users': total_users,
        'load_global_details': load_global_details,
    }
    
    # Cache por 1 minuto
    cache.set(cache_key, context, 60)
    
    return render(request, 'debug_shared.html', context)

@login_required
def create_global_test_data(request):
    """Cria dados de teste para recursos globais"""
    user = request.user
    other_user = User.objects.exclude(id=user.id).first()
    
    if not other_user:
        return JsonResponse({'error': 'Não há outros usuários para testar'})
    
    messages = []
    
    # Criar ferramenta global
    tool, created = Tool.objects.get_or_create(
        name="Ferramenta Global de Teste",
        user=other_user,
        defaults={
            'category': 'Teste',
            'description': 'Esta é uma ferramenta global de teste',
            'is_global': True,
            'global_created_by': other_user
        }
    )
    if created:
        messages.append(f"Ferramenta global '{tool.name}' criada")
    
    # Criar nota global
    note, note_created = Note.objects.get_or_create(
        title="Nota Global de Teste",
        user=other_user,
        defaults={
            'content': 'Conteúdo da nota global de teste',
            'is_global': True,
            'global_created_by': other_user
        }
    )
    if note_created:
        messages.append(f"Nota global '{note.title}' criada")
    
    # Criar arquivo global (simulado)
    file, file_created = File.objects.get_or_create(
        name="Arquivo Global de Teste.txt",
        user=other_user,
        defaults={
            'file': 'test_files/global_test.txt',
            'is_global': True,
            'global_created_by': other_user
        }
    )
    if file_created:
        messages.append(f"Arquivo global '{file.name}' criado")
    
    return JsonResponse({
        'success': True,
        'messages': messages,
        'redirect_url': '/GDriver/shared-with-me/'
    })

@login_required
def load_global_resources_ajax(request):
    """View AJAX para carregar recursos globais sob demanda"""
    resource_type = request.GET.get('type')
    user = request.user
    
    if not resource_type:
        return JsonResponse({'error': 'Tipo de recurso não especificado'}, status=400)
    
    resource_models = {
        'file': File,
        'note': Note,
        'tool': Tool,
        'dork': Dork,
        'resource_link': ResourceLink,
        'youtube_channel': YouTubeChannel,
        'cve': CVE,
    }
    
    if resource_type not in resource_models:
        return JsonResponse({'error': 'Tipo de recurso inválido'}, status=400)
    
    model = resource_models[resource_type]
    
    # Buscar recursos com limites para performance
    resources = model.objects.filter(
        is_global=True
    ).exclude(user=user).select_related('global_created_by', 'user')[:100]
    
    # Serializar dados básicos
    resources_data = []
    for resource in resources:
        resource_data = {
            'id': resource.id,
            'name': getattr(resource, 'name', 
                           getattr(resource, 'title', 
                                  getattr(resource, 'cve_id', str(resource)))),
            'created_by': resource.global_created_by.username if resource.global_created_by else resource.user.username,
            'owner': resource.user.username,
            'created_at': getattr(resource, 'uploaded_at', 
                                 getattr(resource, 'created_at', 
                                        getattr(resource, 'published_date', None))),
        }
        
        # Campos específicos por tipo
        if resource_type == 'file':
            resource_data['size'] = getattr(resource.file, 'size', 0) if resource.file else 0
        elif resource_type == 'dork':
            resource_data['platform'] = resource.platform
            resource_data['query_preview'] = resource.query[:100] + '...' if len(resource.query) > 100 else resource.query
        
        resources_data.append(resource_data)
    
    return JsonResponse({
        'success': True,
        'resource_type': resource_type,
        'resources': resources_data,
        'total_count': len(resources_data)
    })

@login_required
def debug_performance_stats(request):
    """View para estatísticas de performance"""
    user = request.user
    
    # Estatísticas básicas
    stats = {
        'timestamp': timezone.now(),
        'user': f"{user.username} (ID: {user.id})",
    }
    
    # Contagens totais
    stats['total_counts'] = {
        'shared_resources': SharedResource.objects.filter(
            Q(shared_with=user) | Q(shared_with_all=True)
        ).exclude(shared_by=user, shared_with_all=True).count(),
        'global_files': File.objects.filter(is_global=True).exclude(user=user).count(),
        'global_notes': Note.objects.filter(is_global=True).exclude(user=user).count(),
        'global_tools': Tool.objects.filter(is_global=True).exclude(user=user).count(),
        'global_dorks': Dork.objects.filter(is_global=True).exclude(user=user).count(),
        'global_links': ResourceLink.objects.filter(is_global=True).exclude(user=user).count(),
        'global_channels': YouTubeChannel.objects.filter(is_global=True).exclude(user=user).count(),
        'global_cves': CVE.objects.filter(is_global=True).exclude(user=user).count(),
    }
    
    # Recursos criados recentemente
    one_week_ago = timezone.now() - timedelta(days=7)
    stats['recent_activity'] = {
        'shared_resources': SharedResource.objects.filter(created_at__gte=one_week_ago).count(),
        'global_resources': File.objects.filter(is_global=True, uploaded_at__gte=one_week_ago).count() + 
                           Note.objects.filter(is_global=True, created_at__gte=one_week_ago).count() + 
                           Tool.objects.filter(is_global=True, created_at__gte=one_week_ago).count(),
    }
    
    # Estatísticas de usuários
    stats['user_stats'] = {
        'total_users': User.objects.count(),
        'active_sharers': SharedResource.objects.values('shared_by').distinct().count(),
        'active_global_creators': File.objects.filter(is_global=True).values('user').distinct().count(),
    }
    
    return JsonResponse({
        'success': True,
        'performance_stats': stats
    })

@login_required
def clear_debug_cache(request):
    """View para limpar cache do debug"""
    user = request.user
    
    cache_keys_to_delete = [
        f"debug_shared_{user.id}_1",
        f"debug_shared_{user.id}_2",
    ]
    
    deleted_count = 0
    for key in cache_keys_to_delete:
        if cache.delete(key):
            deleted_count += 1
    
    return JsonResponse({
        'success': True,
        'message': f'Cache limpo: {deleted_count} entradas removidas',
        'deleted_count': deleted_count
    })

# ========== SIGNAL PARA COMPARTILHAMENTO ==========

from django.db.models.signals import post_save
from django.dispatch import receiver

@receiver(post_save, sender=File)
def handle_global_file_creation(sender, instance, created, **kwargs):
    """Signal para criar estrutura de compartilhamento quando um arquivo global é criado"""
    if created and instance.is_global:
        # Buscar usuários de uma vez
        all_users = User.objects.exclude(id=instance.user.id).values_list('id', flat=True)
        
        # Criar compartilhamentos (implementar update_shared_file_structure se necessário)
        for user_id in all_users:
            # update_shared_file_structure(User(id=user_id), instance)
            pass

# ========== FUNÇÃO AUXILIAR ==========

def update_shared_file_structure(user, file_instance):
    """
    Função auxiliar para atualizar estrutura de arquivos compartilhados
    (Implementar conforme necessário)
    """
    pass