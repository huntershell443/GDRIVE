from django.urls import path
from .views import (
    signup_view, login_view, logout_view, dashboard_view,
    file_list, upload_file, delete_files,
    notes_list, manage_note, delete_note, manage_folder, delete_folder,
    dork_list, manage_dork, delete_dork, add_dork_note, dork_search,
    cve_list, add_cve,
    tool_list, manage_tool, delete_tool, add_tool_note,
    project_list, manage_project, delete_project, add_project_item, search_all,
    import_cves, download_notes, add_youtube_channel, download_single_note,
    create_folder, delete_folder, import_dorks,
    virtual_terminal, virtual_gui, resource_links_list, add_resource_link,
    # ADICIONE ESTAS NOVAS IMPORTS:
    move_folder, check_file_exists, upload_file_chunked,
    share_resource, shared_with_me, get_shareable_users, youtube_channels_list,
    debug_shared_resources,create_global_test_data, load_global_resources_ajax,
    debug_performance_stats, clear_debug_cache, 
    # ADICIONE ESTAS VIEWS DE NOTAS:
    delete_notes, move_notes_to_folder, move_single_note_to_folder,
    verify_email_view, resend_verification_code,
    download_selected_files,
    import_txt_notes,
)

urlpatterns = [
    path('projects/<int:pk>/terminal/', virtual_terminal, name='virtual_terminal'),
    path('projects/<int:pk>/gui/', virtual_gui, name='virtual_gui'),
    path('search_all/', search_all, name='search_all'),
    
    path('login/', login_view, name='login'),
    path('logout/', logout_view, name='logout'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('files/', file_list, name='file_list'),
    path('upload/', upload_file_chunked, name='upload_file'),
    path('delete-files/', delete_files, name='delete_files'),
    path('download-files/', download_selected_files, name='download_selected_files'),

    path('signup/', signup_view, name='signup'),
    path('verify-email/', verify_email_view, name='verify_email'),
    path('resend-verification/', resend_verification_code, name='resend_verification'),

    # URLs de Notas - CORRIGIDAS E COMPLETAS
    path('notes/', notes_list, name='notes_list'),
    path('notes/add/', manage_note, name='add_note'),
    path('notes/edit/<int:pk>/', manage_note, name='edit_note'),
    path('notes/delete/<int:pk>/', delete_note, name='delete_note'),
    path('notes/delete-selected/', delete_notes, name='delete_notes'),  # NOVA URL
    path('notes/move-multiple/', move_notes_to_folder, name='move_notes_to_folder'),  # NOVA URL
    path('notes/move-single/', move_single_note_to_folder, name='move_single_note_to_folder'),  # NOVA URL
    path('notes/import-txt/', import_txt_notes, name='import_txt_notes'),
    path('notas/download/', download_notes, name='download_notes'),
    path('nota/<int:pk>/download/', download_single_note, name='download_single_note'),

    path('folders/add/', manage_folder, name='add_folder'),
    path('folders/edit/<int:pk>/', manage_folder, name='edit_folder'),
    path('folders/delete/<int:folder_id>/', delete_folder, name='delete_folder'),

    path('dorks/', dork_list, name='dork_list'),
    path('dorks/add/', manage_dork, name='add_dork'),
    path('dorks/edit/<int:pk>/', manage_dork, name='edit_dork'),
    path('dorks/delete/<int:pk>/', delete_dork, name='delete_dork'),
    path('dorks/<int:dork_pk>/add-note/', add_dork_note, name='add_dork_note'),
    path('dorks/search/', dork_search, name='dork_search'),
    path('dorks/import/', import_dorks, name='import_dorks'),

    path('cves/', cve_list, name='cve_list'),
    path('cves/add/', add_cve, name='add_cve'),

    path('tools/', tool_list, name='tool_list'),
    path('tools/add/', manage_tool, name='add_tool'),
    path('tools/edit/<int:pk>/', manage_tool, name='edit_tool'),
    path('tools/delete/<int:pk>/', delete_tool, name='delete_tool'),
    path('tools/<int:tool_pk>/add-note/', add_tool_note, name='add_tool_note'),

    path('projects/', project_list, name='project_list'),
    path('projects/add/', manage_project, name='add_project'),
    path('projects/edit/<int:pk>/', manage_project, name='edit_project'),
    path('projects/delete/<int:pk>/', delete_project, name='delete_project'),
    path('projects/<int:project_pk>/add-item/', add_project_item, name='add_project_item'),
    path('cves/importar/', import_cves, name='import_cves'),

    path('add-youtube-channel/', add_youtube_channel, name='add_youtube_channel'),
    path('youtube-channels/', youtube_channels_list, name='youtube_channels_list'),

    path('folders/create/', create_folder, name='create_folder'),
    path('folders/delete/<int:folder_id>/', delete_folder, name='delete_folder'),

    path('resource-links/', resource_links_list, name='resource_links_list'),
    path('resource-links/add/', add_resource_link, name='add_resource_link'),

    # URLs auxiliares
    path('folders/move/<int:folder_id>/', move_folder, name='move_folder'),
    path('check-file-exists/<int:file_id>/', check_file_exists, name='check_file_exists'),

    # Compartilhamento
    path('share/', share_resource, name='share_resource'),
    path('shared-with-me/', shared_with_me, name='shared_with_me'),
    path('get-shareable-users/', get_shareable_users, name='get_shareable_users'),
    path('debug/shared-resources/', debug_shared_resources, name='debug_shared_resources'),
    path('create-global-test-data/', create_global_test_data, name='create_global_test_data'),
    path('debug/load-global-resources/', load_global_resources_ajax, name='load_global_resources'),
    path('debug/performance-stats/', debug_performance_stats, name='debug_performance_stats'),
    path('debug/clear-cache/', clear_debug_cache, name='clear_debug_cache'),
]