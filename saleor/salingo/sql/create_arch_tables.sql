create table arch_product_product as select * from product_product where 1 = 2;
alter table arch_product_product add constraint a_product_product_pkey primary key (id);
alter table arch_product_product add constraint a_product_product_default_variant_id_key unique (default_variant_id);
alter table arch_product_product add constraint a_product_product_slug_key unique (slug);

create table arch_product_productvariant as select * from product_productvariant where 1 = 2;
alter table arch_product_productvariant add constraint a_product_productvariant_pkey primary key (id);
alter table arch_product_productvariant add constraint a_product_productvariant_sku_key unique (sku);

create table arch_product_productimage as select * from product_productimage where 1 = 2;
alter table arch_product_productimage add constraint a_product_productimage_pkey primary key (id);
