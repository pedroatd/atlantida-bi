-- Contrato del enriquecimiento de reseñas por aspectos (lo rellena el módulo de IA; vacío hasta
-- entonces). dbt lo lee para el semáforo de aspectos y el KPI dias_max_aspecto_en_rojo.
create table if not exists ml.resena_aspecto (
  review_id    bigint not null,
  aspecto      text not null,
  polaridad    smallint not null check (polaridad in (-1, 0, 1)),
  modelo       text not null,
  procesado_en timestamptz not null default now(),
  primary key (review_id, aspecto, modelo)
);
comment on table ml.resena_aspecto is
  'Aspecto y polaridad (-1, 0, 1) de cada reseña según un modelo; una fila por reseña, aspecto y modelo.';
grant select, insert, update, delete on ml.resena_aspecto to ml_writer;
grant usage on schema ml to transformer;
grant select on ml.resena_aspecto to transformer, bi_reader;
alter default privileges for role ml_writer in schema ml grant select on tables to transformer;

-- Contrato de las salidas de la IA que lee dbt (las escribe el módulo de IA; vacías hasta
-- entonces, los modelos que las leen dan cero filas). Ver 09-ia.sql.
alter table ml.resena_aspecto add column if not exists huella_texto text;
alter table ml.resena_aspecto add column if not exists version_modelo text;
alter table ml.resena_aspecto add column if not exists confianza real;
comment on column ml.resena_aspecto.huella_texto is 'md5 del texto clasificado: dbt solo usa la fila si coincide con el texto actual.';

create table if not exists ml.prevision_ocupacion (
  hotel_id       bigint not null,
  fecha          date not null,
  origen         date not null,
  metodo         text not null,
  horizonte_dias integer not null,
  ocupacion      real not null,
  inferior       real,
  superior       real,
  procesado_en   timestamptz not null default now(),
  primary key (hotel_id, fecha, origen, metodo)
);
comment on table ml.prevision_ocupacion is 'Ocupación prevista por hotel y noche desde la fecha de origen (pickup, AutoETS y estacional ingenuo).';

create table if not exists ml.anomalia_kpi (
  fecha        date not null,
  ambito       text not null,
  kpi          text not null,
  metodo       text not null,
  valor        double precision,
  esperado     double precision,
  puntuacion   double precision,
  es_anomalia  boolean not null,
  procesado_en timestamptz not null default now(),
  primary key (fecha, ambito, kpi, metodo)
);
comment on table ml.anomalia_kpi is 'Días anómalos de los KPI diarios (puntuación robusta frente al mismo día de las semanas anteriores).';

create table if not exists meta.modelo_ia (
  modelo              text not null,
  tarea               text not null,
  version             text not null,
  proveedor           text not null,
  modo                text not null,
  oficial             boolean not null default false,
  externo             boolean not null default false,
  datos_entrenamiento text,
  parametros          jsonb not null default '{}',
  metricas            jsonb not null default '{}',
  limitaciones        text not null,
  registrado_en       timestamptz not null default now(),
  primary key (modelo, tarea)
);
comment on table meta.modelo_ia is 'Ficha de cada modelo de IA (model card): versión, proveedor, modo, si es el oficial, si envía datos fuera, datos de entrenamiento, métricas principales y limitaciones.';

grant select, insert, update, delete on ml.prevision_ocupacion, ml.anomalia_kpi, meta.modelo_ia
  to ml_writer;
grant select on ml.prevision_ocupacion, ml.anomalia_kpi, meta.modelo_ia to transformer, bi_reader;
