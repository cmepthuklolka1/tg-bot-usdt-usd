from tenacity import retry, stop_after_attempt, wait_exponential

DEFAULT_RETRY = retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=2, min=3, max=15))
CBRF_RETRY = retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
