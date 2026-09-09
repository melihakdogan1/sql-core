.PHONY: up down migrate seed reset count

up:
	docker compose -f docker/docker-compose.yml up -d

down:
	docker compose -f docker/docker-compose.yml down

migrate:
	docker exec -i sql_core_pg psql -U dev_user -d ecommerce_oltp < migrations/001_initial_schema.sql

seed: up migrate
	uv run python scripts/seed.py

count:
	docker exec -it sql_core_pg psql -U dev_user -d ecommerce_oltp -c "\
	SELECT 'users' as tbl, count(*) from users union all \
	SELECT 'categories', count(*) from categories union all \
	SELECT 'products', count(*) from products union all \
	SELECT 'coupons', count(*) from coupons union all \
	SELECT 'orders', count(*) from orders union all \
	SELECT 'order_items', count(*) from order_items union all \
	SELECT 'payments', count(*) from payments union all \
	SELECT 'shipments', count(*) from shipments union all \
	SELECT 'reviews', count(*) from reviews union all \
	SELECT 'inventory_movements', count(*) from inventory_movements;"

report:
	uv run python scripts/generate_report.py

elt:
	uv run python scripts/elt_pipeline.py