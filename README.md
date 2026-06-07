```
» docker network create ezchess

» docker run -d --network ezchess --name db -e POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=ezchess postgres:15-alpine

» docker run -d --network ezchess --name ezchess -p 3000:3000 -e DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/ezchess -e OPENAI_API_KEY=*** zeroshubham/ezchess:latest

```