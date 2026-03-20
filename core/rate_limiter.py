import time
from typing import Dict, Tuple
from fastapi import HTTPException, Request, status

class RateLimiter:
    """
    Simple In-Memory Fixed Window Rate Limiter.
    Logic:
    - Tracks requests per IP address.
    - Resets the count after a specific 'window' of time.
    - If requests exceed 'max_requests', raises a 429 Too Many Requests.
    """
    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # Structure: { ip_address: (request_count, window_start_time) }
        self.requests: Dict[str, Tuple[int, float]] = {}

    async def __call__(self, request: Request):
        client_ip = request.client.host
        current_time = time.time()

        if client_ip not in self.requests:
            # First request from this IP
            self.requests[client_ip] = (1, current_time)
            return

        count, start_time = self.requests[client_ip]

        if current_time - start_time > self.window_seconds:
            # Window has expired, reset for this IP
            self.requests[client_ip] = (1, current_time)
        else:
            if count >= self.max_requests:
                # Limit exceeded
                retry_after = int(self.window_seconds - (current_time - start_time))
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "message": "Too many requests. Please try again later.",
                        "retry_after_seconds": retry_after
                    },
                    headers={"Retry-After": str(retry_after)}
                )
            # Increment count
            self.requests[client_ip] = (count + 1, start_time)

# Pre-defined limiters for different use cases
login_rate_limiter = RateLimiter(max_requests=5, window_seconds=60) # 5 attempts per minute
general_api_limiter = RateLimiter(max_requests=100, window_seconds=60) # 100 requests per minute
