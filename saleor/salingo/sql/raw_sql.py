duplicated_products = """
    with duble as (
        select product_id, count(*)
        from product_productvariant pp
        group by 1
        having count(*) > 1
    )
    ,leads as (
         select pp.id, sku, pp.created  as data, pp.name, regexp_replace(sku,'-','','g')::numeric sku_num,
         lead (pp."name")  over (order by sku ) as name_next,
         lead (regexp_replace(sku,'-','','g')::numeric )  over (order by sku ) as sku_num_next,
         pp.private_metadata as p_private_metadata,
         pp2.private_metadata as v_private_metadata
         from product_productvariant pp2, product_product pp, duble d
         where pp2.product_id  = pp.id
         and pp.id  = d.product_id
         and substring(sku,1,2) in %s
    ), do_usuniecia as (
        select id as product_id, sku, data, name
        from leads
        where name = name_next
        and sku_num_next - sku_num = 1
        and v_private_metadata->>'location' is null
        and coalesce (p_private_metadata->>'publish.allegro.status','null') not in ('published','sold')
        order by sku
    )
    select * from do_usuniecia order by data"""


products_media_to_remove_background = """
    select
    ppm.id,
    ppm.image,
    ppm.ppoi
    from
    product_product pp,
    product_productmedia ppm,
    product_producttype ppt,
    product_productvariant ppv,
    attribute_assignedproductattribute aapa,
    attribute_assignedproductattributevalue aapav,
    attribute_attributevalue aav,
    attribute_attribute aa
    where
    pp.id = ppm.product_id
    and pp.product_type_id = ppt.id
    and pp.id = ppv.product_id
    and pp.id = aapa.product_id
    and aapa.id = aapav.assignment_id
    and aapav.value_id = aav.id
    and aav.attribute_id = aa.id
    and cast(pp.created as date) between %s and %s
    and aa."name" = 'Kolor'
    and aav."name" != 'biały'
    and ppt."name" not like 'Biustonosz%%'
    and ppm.oembed_data ->>'background_remove_status' is null
    order by ppv.sku
    """


variant_id_sale_name = """
    SELECT dsv.productvariant_id, ds."name"
    FROM discount_sale_variants dsv
    join discount_sale ds
    on dsv.sale_id = ds.id
    WHERE dsv.productvariant_id in %s
"""
