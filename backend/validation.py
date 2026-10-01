"""Render request errors without echoing non-JSON values or source content."""
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


async def request_validation_error(_request, exc: RequestValidationError):
    # Pydantic includes the rejected value in errors. NaN/Infinity can reach
    # the JSON parser but cannot be serialized by Starlette's JSONResponse.
    errors = [{key: error[key] for key in ('type', 'loc', 'msg') if key in error}
              for error in exc.errors()]
    return JSONResponse(status_code=422, content={'detail': errors})
