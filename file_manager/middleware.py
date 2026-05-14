from django.http import HttpResponseNotFound, HttpResponseServerError
from django.template import loader

class ErrorHandlerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        
        if response.status_code == 404:
            return self.handle_404(request)
        elif response.status_code == 500:
            return self.handle_500(request)
            
        return response

    def handle_404(self, request):
        try:
            template = loader.get_template('404.html')
            return HttpResponseNotFound(template.render())
        except:
            return HttpResponseNotFound("""
            <html><body>
            <h1>404 - Página Não Encontrada</h1>
            <p>A página que você está procurando não existe.</p>
            <a href="/">Voltar para o Login</a>
            </body></html>
            """)

    def handle_500(self, request):
        try:
            template = loader.get_template('500.html')
            return HttpResponseServerError(template.render())
        except:
            return HttpResponseServerError("""
            <html><body>
            <h1>500 - Erro Interno do Servidor</h1>
            <p>Ocorreu um erro inesperado.</p>
            <a href="/">Voltar para o Login</a>
            </body></html>
            """)