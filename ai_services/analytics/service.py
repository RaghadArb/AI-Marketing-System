from .performance_analyzer import PerformanceAnalyzer
from .customer_support_analyzer import CustomerSupportAnalyzer
from .report_generator import ReportGenerator
from .charts import AnalyticsCharts

# service layer to combine the pipeline of showing the analysis of a campaign
# because the view is not supposed to know about pandas, dataframe and analytics files
# it should only call AnalyticsService and receive the final result


class AnalyticsService:


    def __init__(self):
        
        # the campaign data analysis
        self.performance_analyzer = PerformanceAnalyzer()
        
        # the customer support analysis
        self.support_analyzer = CustomerSupportAnalyzer()
        
        # final reports generation
        self.report_generator = ReportGenerator()
        
        # to generate the charts from the analysis reports
        self.charts = AnalyticsCharts()



    def get_campaign_analytics(self, campaign):

        analysis = self.performance_analyzer.analyze_campaign(
            campaign
        )


        report = self.report_generator.generate_campaign_report(
            analysis["summary"]
        )

        charts = [
        self.charts.create_platform_performance_chart(
            analysis["dataframe"]
        ),

        self.charts.create_ctr_chart(
            analysis["dataframe"]
        )
        ]

        return {

            "summary": analysis["summary"],

            "report": report,

            "data": analysis["dataframe"].to_dict(
                orient="records"
            ),
            
            "charts": charts

        }



    def get_support_analytics(self, company):

        analysis = self.support_analyzer.analyze_company_support(
            company
        )


        report = self.report_generator.generate_support_report(
            analysis["summary"]
        )


        return {

            "summary": analysis["summary"],

            "report": report,

            "data": analysis["dataframe"].to_dict(
                orient="records"
            )

        }