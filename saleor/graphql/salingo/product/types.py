import graphene


class SitemapSlugs(graphene.ObjectType):
    productSlugs = graphene.List(graphene.String)
    categoriesSlugs = graphene.List(graphene.String)
    pagesSlugs = graphene.List(graphene.String)

    class Meta:
        description = ("Lists of slugs for sitemap generation")
