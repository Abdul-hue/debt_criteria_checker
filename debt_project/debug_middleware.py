
class RequestDebugMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        print(f"\n[BACKEND DEBUG] {request.method} {request.path}")
        response = self.get_response(request)
        print(f"[BACKEND DEBUG] Status: {response.status_code}")
        return response
