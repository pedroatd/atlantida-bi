-- Base de metadatos operativa: cada carga deja rastro. Ver capítulo 11.
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
grant select, insert, update on meta.carga to loader;
grant usage on sequence meta.carga_id_seq to loader;
grant select on meta.carga to transformer, bi_reader;
