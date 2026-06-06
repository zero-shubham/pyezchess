from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse

router = APIRouter(tags=["docs"])


SWAGGER_UI_HTML = """<!DOCTYPE html>
<html>
<head>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
    <title>ezchess API Docs</title>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
    <script>
        SwaggerUIBundle({
            url: "/api/v1/openapi.json",
            dom_id: "#swagger-ui",
        });
    </script>
</body>
</html>"""


@router.get("/docs", include_in_schema=False)
async def swagger_ui():
    return HTMLResponse(content=SWAGGER_UI_HTML)


@router.get("/redoc", include_in_schema=False)
async def redoc_ui():
    return HTMLResponse(content="""<!DOCTYPE html>
<html>
<head>
    <title>ezchess API Docs</title>
    <script src="https://cdn.jsdelivr.net/npm/redoc@next/bundles/redoc.standalone.js"></script>
</head>
<body>
    <div id="redoc"></div>
    <script>
        Redoc.init("/api/v1/openapi.json", {}, document.getElementById("redoc"));
    </script>
</body>
</html>""")


@router.get("/api/v1/openapi.json", include_in_schema=False)
async def openapi_json():
    from server.main import app
    return JSONResponse(content=app.openapi())
