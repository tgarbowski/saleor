create table arch_product_product as select * from product_product where 1 = 2;
alter table arch_product_product add constraint a_product_product_pkey primary key (id);
alter table arch_product_product add constraint a_product_product_default_variant_id_key unique (default_variant_id);
alter table arch_product_product add constraint a_product_product_slug_key unique (slug);
alter table arch_product_product add column archived_at timestamp default now();

create table arch_product_productvariant as select * from product_productvariant where 1 = 2;
alter table arch_product_productvariant add constraint a_product_productvariant_pkey primary key (id);
alter table arch_product_productvariant add constraint a_product_productvariant_sku_key unique (sku);
alter table arch_product_productvariant add column archived_at timestamp default now();

create table arch_product_productmedia as select * from product_productmedia where 1 = 2;
alter table arch_product_productmedia add constraint a_product_productmedia_pkey primary key (id);
alter table arch_product_productmedia add column archived_at timestamp default now();
