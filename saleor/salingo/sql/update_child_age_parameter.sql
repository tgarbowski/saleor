with recursive categories as (
    select  id, "name", parent_id, "level"
    from product_category
    where slug in ('dziecko-odziez-niemowleca', 'dziecko-odziez-dziecieca', 'dziecko-bielizna-dziecieca')
    union all
    select pc.id, pc.name, pc.parent_id, pc."level"
    from categories c, product_category pc
    where pc.parent_id = c.id
)
update product_producttype set metadata = jsonb_insert(metadata, '{allegro.mapping.attributes,0}','["Wiek dziecka", "rozmiar-dzieci"]')
where metadata->>'categoryId' in (select  encode(('Category:'||id::text)::bytea,'base64') from categories)
and metadata->>'allegro.mapping.attributes' not like '%Wiek dziecka%'
