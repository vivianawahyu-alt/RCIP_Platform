.PHONY: up down logs migrate seed test web clean demo-data validate evaluate docs-gen backup
up:
	docker compose up -d --build
down:
	docker compose down
logs:
	docker compose logs -f api worker
migrate:
	docker compose exec api alembic upgrade head
seed:
	docker compose exec api python -m seed.run
test:
	docker compose exec api pytest -q
web:
	cd web && npm install && npm run dev
clean:
	docker compose down -v
demo-data:   # HANYA pada DB kosong (setelah migrate, tanpa seed): korpus 30 dokumen + seluruh status
	docker compose exec api python -m seed.generate --seed 42
validate:
	docker compose exec api python -m seed.validate
evaluate:
	docker compose exec api python -m app.ai.evaluate
docs-gen:
	docker compose exec api python -m seed.data_dictionary
backup:
	docker exec rcip_postgres pg_dump -U rcip -d rcip_db > rcip_backup_$$(date +%Y%m%d_%H%M).sql
