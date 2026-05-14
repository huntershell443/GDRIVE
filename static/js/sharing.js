// static/js/sharing.js

// Função para obter o token CSRF
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Função para abrir modal de compartilhamento
function openShareModal(resourceType, resourceId, resourceName) {
    console.log(`DEBUG: Abrindo modal para ${resourceType} ID ${resourceId} - ${resourceName}`);
    
    // Definir os valores no formulário
    document.getElementById('shareResourceType').value = resourceType;
    document.getElementById('shareResourceId').value = resourceId;
    
    // Atualizar título do modal se quiser
    document.querySelector('#shareModal .modal-title').textContent = 
        `Compartilhar ${resourceName}`;

    // Carregar usuários disponíveis
    fetch('/share/get-users/')
        .then(response => {
            if (!response.ok) {
                throw new Error('Erro ao carregar usuários');
            }
            return response.json();
        })
        .then(data => {
            const userSelect = document.getElementById('shareUsers');
            userSelect.innerHTML = '';
            
            if (data.users && data.users.length > 0) {
                data.users.forEach(user => {
                    const option = document.createElement('option');
                    option.value = user.id;
                    option.textContent = `${user.username} (${user.email})`;
                    userSelect.appendChild(option);
                });
                console.log(`DEBUG: ${data.users.length} usuários carregados`);
            } else {
                console.log('DEBUG: Nenhum usuário disponível para compartilhamento');
            }
        })
        .catch(error => {
            console.error('Erro ao carregar usuários:', error);
            alert('Erro ao carregar lista de usuários');
        });

    // Mostrar o modal
    const shareModal = new bootstrap.Modal(document.getElementById('shareModal'));
    shareModal.show();
}

// Função para enviar compartilhamento
function submitShare() {
    const resourceType = document.getElementById('shareResourceType').value;
    const resourceId = document.getElementById('shareResourceId').value;
    const shareScope = document.querySelector('input[name="share_scope"]:checked').value;
    const permission = document.querySelector('select[name="permission"]').value;
    
    const userSelect = document.getElementById('shareUsers');
    const selectedUsers = Array.from(userSelect.selectedOptions).map(option => option.value);
    
    const isPublic = shareScope === 'public';
    
    console.log('DEBUG: Enviando compartilhamento:', {
        resourceType,
        resourceId,
        isPublic,
        permission,
        selectedUsers
    });

    const formData = new FormData();
    formData.append('resource_type', resourceType);
    formData.append('resource_id', resourceId);
    formData.append('shared_with_all', isPublic);
    formData.append('permission', permission);
    
    // Adicionar usuários selecionados (apenas se não for público)
    if (!isPublic) {
        selectedUsers.forEach(userId => {
            formData.append('users', userId);
        });
    }

    // Mostrar loading
    const shareButton = document.querySelector('#shareModal .btn-primary');
    const originalText = shareButton.innerHTML;
    shareButton.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Compartilhando...';
    shareButton.disabled = true;

    fetch('/share/resource/', {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
        },
        body: formData
    })
    .then(response => {
        if (!response.ok) {
            throw new Error('Erro na resposta do servidor');
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            alert(data.message);
            $('#shareModal').modal('hide');
            
            // Recarregar após 1 segundo se estiver na página de compartilhados
            if (window.location.pathname.includes('shared-with-me')) {
                setTimeout(() => {
                    window.location.reload();
                }, 1000);
            }
        } else {
            throw new Error(data.error || 'Erro desconhecido');
        }
    })
    .catch(error => {
        console.error('Erro ao compartilhar:', error);
        alert('Erro ao compartilhar recurso: ' + error.message);
    })
    .finally(() => {
        // Restaurar botão
        shareButton.innerHTML = originalText;
        shareButton.disabled = false;
    });
}

// Event listener para mudança no scope do compartilhamento
document.addEventListener('DOMContentLoaded', function() {
    const sharePublicRadio = document.getElementById('sharePublic');
    const shareSpecificRadio = document.getElementById('shareSpecific');
    const usersSelection = document.getElementById('usersSelection');
    
    if (sharePublicRadio && shareSpecificRadio && usersSelection) {
        function toggleUsersSelection() {
            if (shareSpecificRadio.checked) {
                usersSelection.style.display = 'block';
            } else {
                usersSelection.style.display = 'none';
            }
        }
        
        sharePublicRadio.addEventListener('change', toggleUsersSelection);
        shareSpecificRadio.addEventListener('change', toggleUsersSelection);
        
        // Inicializar estado
        toggleUsersSelection();
    }
});