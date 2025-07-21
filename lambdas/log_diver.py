import os
import json
import boto3
import io
from collections import defaultdict
from fpdf import FPDF
from datetime import datetime
from aws_lambda_powertools import Logger
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    ListFlowable,
    ListItem,
)
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.charts.textlabels import Label
from reportlab.graphics import renderPDF

logger = Logger(service="log_diver")

logs = boto3.client("logs")
s3 = boto3.client("s3")
bedrock = boto3.client("bedrock-runtime", region_name="us-west-2")


def safe_text(text):
    return text.replace("\u2022", "*")


def query_access_logs(service_log_group, status_prefix, start_time, now):
    query = f"""
    fields @timestamp, @message
    | filter status like /{status_prefix}\\d\\d/
    | sort @timestamp desc
    | limit 100
    """
    try:
        start_query = logs.start_query(
            logGroupName=service_log_group,
            startTime=start_time,
            endTime=now,
            queryString=query,
        )
        query_id = start_query["queryId"]
    except Exception as e:
        logger.error(f"Error starting CloudWatch Logs Insights query: {str(e)}")
        raise

    response = {}
    try:
        for _ in range(30):
            resp = logs.get_query_results(queryId=query_id)
            if resp["status"] == "Complete":
                response = resp
                break
    except Exception as e:
        logger.error(f"Error getting CloudWatch Logs Insights results: {str(e)}")
        raise
    return response


def aggregate_user_errors(response):
    user_errors = defaultdict(
        lambda: {
            "email": "-",
            "name": "-",
            "count": 0,
            "resourcePaths": set(),
            "xrayTraceIds": set(),
        }
    )
    users_affected_details = {}
    xray_trace_ids = []
    service_log_map = {}
    for result in response.get("results", []):
        log_data = None
        for field in result:
            logger.info(f"Processing log: {field}")
            if field["field"] == "@message":
                try:
                    log_data = json.loads(field["value"])
                except Exception as e:
                    logger.warning(
                        f"Failed to parse log message: {field['value']}, error: {str(e)}"
                    )
                    continue
        if log_data:
            user_id = log_data.get("user_id", "-")
            email = log_data.get("email", "-")
            name = log_data.get("name", "-")
            resourcePath = log_data.get("resourcePath", "-")
            xray_trace_id = log_data.get("xrayTraceId")
            if xray_trace_id:
                xray_trace_ids.append(xray_trace_id)
                service_log_map[xray_trace_id] = log_data
            if user_id != "-":
                user_errors[user_id]["email"] = email
                user_errors[user_id]["name"] = name
                user_errors[user_id]["count"] += 1
                user_errors[user_id]["resourcePaths"].add(resourcePath)
                if xray_trace_id:
                    user_errors[user_id]["xrayTraceIds"].add(xray_trace_id)
                users_affected_details[user_id] = {"email": email, "name": name}
    return user_errors, users_affected_details, xray_trace_ids, service_log_map


def query_application_logs(app_log_group, clean_trace_id, start_time, now):
    app_query = f'fields @timestamp, @message | filter xray_trace_id = "{clean_trace_id}" | sort @timestamp desc | limit 50'
    app_logs = []
    try:
        start_app_query = logs.start_query(
            logGroupName=app_log_group,
            startTime=start_time,
            endTime=now,
            queryString=app_query,
        )
        app_query_id = start_app_query["queryId"]
        for _ in range(30):
            app_resp = logs.get_query_results(queryId=app_query_id)
            if app_resp["status"] == "Complete":
                app_logs = [
                    field["value"]
                    for result in app_resp.get("results", [])
                    for field in result
                    if field["field"] == "@message"
                ]
                break
        logger.info(
            f"Found {len(app_logs)} application log entries for xray_trace_id {clean_trace_id}."
        )
    except Exception as e:
        logger.error(f"Error querying application logs: {str(e)}")
        raise
    return app_logs


def get_bedrock_summary(sample_xray_trace_id, service_log_map, app_logs):
    bedrock_summary = ""
    if sample_xray_trace_id and sample_xray_trace_id in service_log_map:
        bedrock_input = {
            "service_log": service_log_map[sample_xray_trace_id],
            "application_logs": app_logs,
        }
        prompt = (
            "Human: Given the following API Gateway access log and application logs, "
            "analyze and summarize the root cause of the error in plain English. "
            "Do not include customer impact, only focus on technical diagnosis and likely cause:\n"
            f"{json.dumps(bedrock_input)}\n\nAssistant:"
        )
        try:
            response = bedrock.invoke_model(
                modelId="anthropic.claude-v2",
                contentType="application/json",
                accept="application/json",
                body=json.dumps({"prompt": prompt, "max_tokens_to_sample": 512}),
            )
            response_body = response["body"].read()
            result = json.loads(response_body)
            bedrock_summary = result.get("completion", "")
            logger.info(f"Received Bedrock summary: {bedrock_summary}")
        except Exception as e:
            bedrock_summary = f"Bedrock analysis failed: {str(e)}"
            logger.error(f"Bedrock analysis failed: {str(e)}")
    return bedrock_summary


def generate_reportlab_chart(user_labels, error_counts):
    drawing = Drawing(400, 200)
    bc = VerticalBarChart()
    bc.x = 50
    bc.y = 40
    bc.height = 120
    bc.width = 300
    bc.data = [error_counts]
    bc.strokeColor = colors.black
    bc.valueAxis.valueMin = 0
    bc.valueAxis.valueMax = max(error_counts) if error_counts else 1
    bc.valueAxis.valueStep = max(1, int((max(error_counts) if error_counts else 1) / 5))
    bc.categoryAxis.labels.boxAnchor = "ne"
    bc.categoryAxis.categoryNames = user_labels
    bc.barWidth = 20
    bc.barSpacing = 10
    bc.bars[0].fillColor = colors.lightblue
    drawing.add(bc)
    label = Label()
    label.setOrigin(200, 180)
    label.boxAnchor = "n"
    label.setText("Errors per User")
    drawing.add(label)
    return drawing


def generate_pdf(
    stage,
    error_type,
    user_ids,
    error_counts,
    user_labels,
    user_errors,
    bedrock_summary,
    app_logs,
    sample_xray_trace_id,
):
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    story = []

    title = Paragraph(
        f"<b>WorkoutTracer Investigation Report - {stage} ({error_type})</b>",
        styles["Title"],
    )
    story.append(title)
    story.append(Spacer(1, 12))

    story.append(Paragraph("<b>Customer Impact Visualization:</b>", styles["Heading2"]))
    story.append(Spacer(1, 6))

    if user_ids and error_counts:
        chart = generate_reportlab_chart(user_labels, error_counts)
        story.append(chart)
        story.append(Spacer(1, 18))
    else:
        story.append(Paragraph("No affected users found.", styles["Normal"]))
        story.append(Spacer(1, 12))

    story.append(Paragraph("<b>Affected Users Details:</b>", styles["Heading2"]))
    story.append(Spacer(1, 6))
    for user_id, info in user_errors.items():
        user_bullets = [
            Paragraph(f"<b>User:</b> {info['name']}", styles["Normal"]),
            Paragraph(f"Email: {info['email']}", styles["Normal"]),
            Paragraph(f"Errors: {info['count']}", styles["Normal"]),
            Paragraph(
                f"ResourcePaths: {', '.join(info['resourcePaths'])}", styles["Normal"]
            ),
            Paragraph(
                f"X-Ray Trace IDs: {', '.join(info['xrayTraceIds'])}", styles["Normal"]
            ),
        ]
        story.append(
            ListFlowable(
                [ListItem(bullet) for bullet in user_bullets], bulletType="bullet"
            )
        )
        story.append(Spacer(1, 6))

    story.append(Paragraph("<b>Bedrock Analysis:</b>", styles["Heading2"]))
    story.append(Paragraph(bedrock_summary, styles["Normal"]))
    story.append(Spacer(1, 12))

    story.append(
        Paragraph("<b>Application Logs Sent to Bedrock:</b>", styles["Heading2"])
    )
    if app_logs:
        for log in app_logs:
            story.append(Paragraph(log, styles["Code"]))
            story.append(Spacer(1, 2))
    else:
        story.append(
            Paragraph(
                "No application logs found for the selected request.", styles["Normal"]
            )
        )

    doc.build(story)
    pdf_buffer.seek(0)
    return pdf_buffer


def lambda_handler(event, context):
    stage = os.environ.get("STAGE")
    error_type = event.get("error_type")
    if error_type not in ("client", "server"):
        logger.error(f"Invalid error_type received: {error_type}")
        return {"error": "You must pass 'error_type' as either 'client' or 'server'."}
    status_prefix = "4" if error_type == "client" else "5"
    folder = "client" if error_type == "client" else "server"

    time_since_minutes = event.get("time_since", 30)
    try:
        time_since_minutes = int(time_since_minutes)
    except Exception:
        time_since_minutes = 30

    service_log_group = f"/aws/apigateway/WorkoutTracer-ServiceLogs-{stage}"
    app_log_group = f"/aws/lambda/WorkoutTracer-ApiLambda-{stage}"
    bucket_name = f"workouttracer-investigations-{stage.lower()}"

    now = int(datetime.utcnow().timestamp())
    start_time = max(0, now - time_since_minutes * 60)

    response = query_access_logs(service_log_group, status_prefix, start_time, now)
    user_errors, users_affected_details, xray_trace_ids, service_log_map = (
        aggregate_user_errors(response)
    )

    logger.info(f"Found {len(user_errors)} unique users affected.")
    logger.info(f"X-Ray Trace IDs found: {xray_trace_ids}")
    logger.info(f"Users affected: {list(user_errors.keys())}")
    logger.info(f"Users affected details: {users_affected_details}")

    table_rows = []
    for user_id, info in user_errors.items():
        table_rows.append(
            [
                user_id,
                info["email"],
                info["name"],
                info["count"],
                ", ".join(info["resourcePaths"]),
                ", ".join(info["xrayTraceIds"]),
            ]
        )

    sample_xray_trace_id = xray_trace_ids[0] if xray_trace_ids else None
    app_logs = []
    if sample_xray_trace_id:
        clean_trace_id = sample_xray_trace_id.replace("Root=", "")
        app_logs = query_application_logs(
            app_log_group, clean_trace_id, start_time, now
        )

    bedrock_summary = get_bedrock_summary(
        sample_xray_trace_id, service_log_map, app_logs
    )

    user_ids = []
    error_counts = []
    user_labels = []
    for user_id, info in user_errors.items():
        user_ids.append(user_id)
        error_counts.append(info["count"])
        label = f"{info['name']} ({info['email']})"
        user_labels.append(label)

    pdf_output = generate_pdf(
        stage,
        error_type,
        user_ids,
        error_counts,
        user_labels,
        user_errors,
        bedrock_summary,
        app_logs,
        sample_xray_trace_id,
    )

    try:
        s3.head_bucket(Bucket=bucket_name)
    except Exception as e:
        logger.warning(
            f"S3 bucket {bucket_name} does not exist, creating. Error: {str(e)}"
        )
        region = os.environ.get("AWS_REGION", "us-west-2")
        if region == "us-east-1":
            s3.create_bucket(Bucket=bucket_name)
        else:
            s3.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": region},
            )

    dt_str = datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%SZ")
    key = f"{folder}/report-{dt_str}.pdf"
    try:
        s3.put_object(
            Bucket=bucket_name, Key=key, Body=pdf_output, ContentType="application/pdf"
        )
        logger.info(f"PDF report saved to S3: s3://{bucket_name}/{key}")
    except Exception as e:
        logger.error(f"Failed to save PDF to S3: {str(e)}")
        raise

    return {
        "bucket": bucket_name,
        "key": key,
        "user_error_table": table_rows,
        "bedrock_summary": bedrock_summary,
        "users_affected_details": users_affected_details,
    }
