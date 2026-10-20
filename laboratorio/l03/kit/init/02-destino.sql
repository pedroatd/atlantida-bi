-- Destino de la carga en crudo: raw (las tablas tal como llegan) y meta (rastro de cada carga).
create schema if not exists raw;
create schema if not exists meta;

-- Cada carga deja rastro: una fila por tabla y ejecución (las mismas columnas que la plataforma).
create table if not exists meta.carga (
  id        bigint generated always as identity primary key,
  fuente    text not null,
  tabla     text not null,
  inicio    timestamptz not null default now(),
  fin       timestamptz,
  filas     bigint,
  estado    text not null check (estado in ('en_curso', 'ok', 'error', 'instantanea')),
  detalle   jsonb not null default '{}'
);
