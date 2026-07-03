let
    Source = PostgreSQL.Database("localhost", "srpe_etl", [CreateNavigationProperties = false]),
    vw_sales_detail = Source{[Schema="public",Item="vw_sales_detail"]}[Data]
in
    vw_sales_detail
