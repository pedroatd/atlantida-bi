-- Una capa = un esquema. Ver capítulo 11 (arquitectura de referencia).
create schema if not exists raw_pms;
create schema if not exists raw_ext;
create schema if not exists staging;
create schema if not exists snapshots;
create schema if not exists intermediate;
create schema if not exists marts_core;
create schema if not exists marts_revenue;
create schema if not exists marts_marketing;
create schema if not exists marts_experiencia;
create schema if not exists marts_kpi;
create schema if not exists vault;
create schema if not exists ml;
create schema if not exists meta;
