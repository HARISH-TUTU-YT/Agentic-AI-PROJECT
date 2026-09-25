import os
import sys

# Setup Django environment for standalone and MCP execution
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'InventoryCore.settings')
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

import django
django.setup()

from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
load_dotenv()

from emails import EmailSender
from mcp.server.fastmcp import FastMCP
from services import (
    InventoryManager,
    StageManager,
    ProductManager,
    MachineManager,
    ShiftManager,
    OrderManager,
    seed_services
)

# Initialize Domain Services
inventory_manager = InventoryManager()
stage_manager = StageManager()
product_manager = ProductManager()
machine_manager = MachineManager()
shift_manager = ShiftManager()
order_manager = OrderManager()

# Seed baseline facilities, stages, and essential metadata
seed_services(
    inventory_manager,
    stage_manager,
    product_manager,
    machine_manager,
    shift_manager,
    order_manager
)

emailer = EmailSender(
    smtp_server="smtp.gmail.com",
    port=587,
    username=os.getenv("CB_EMAIL"),
    password=os.getenv("CB_EMAIL_PWD"),
    use_tls=True
)

# Initialize FastMCP Server
mcp = FastMCP("dine-inventory-assist")


# ---------------------------------------------------------
# Communication & Notification Tools
# ---------------------------------------------------------

@mcp.tool()
def send_email(to_emails: List[str], subject: str, body: str, html: bool = False) -> str:
    """
    Send an email notification or alert to one or more recipients.
    :param to_emails: List of recipient email addresses
    :param subject: Email subject line
    :param body: Body content of the email
    :param html: Whether content is HTML (default False)
    :return: Confirmation message
    """
    return emailer.send_email(subject=subject, body=body, to_emails=to_emails, html=html)



# ---------------------------------------------------------
# Inventory & Raw Material Tools
# ---------------------------------------------------------

@mcp.tool()
def add_raw_material(
    name: str,
    quantity: int,
    quantity_metric: str = "Kilogram",
    usage: int = 1,
    usage_metric: str = "Kg",
    plant_id: int = 1
) -> str:
    """
    Add a new raw material or product item to a plant inventory.
    :param name: Name of the raw material (e.g., Paneer, Tomato, Milk)
    :param quantity: Available quantity number
    :param quantity_metric: Metric (Unit, Gram, Kilogram, Ltr, Ml)
    :param usage: Usage quantity
    :param usage_metric: Usage metric (Unit, Gram, Ml, Piece)
    :param plant_id: ID of the plant/branch (default 1)
    :return: Confirmation message
    """
    return inventory_manager.add_raw_material(
        name=name,
        quantity=quantity,
        quantity_metric=quantity_metric,
        usage=usage,
        usage_metric=usage_metric,
        plant_id=plant_id
    )


@mcp.tool()
def get_raw_material_details(name: str, plant_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Get raw material/product details by name.
    :param name: Material name to search
    :param plant_id: Optional plant ID filter
    :return: Material details dictionary
    """
    return inventory_manager.get_raw_material_details(name=name, plant_id=plant_id)


@mcp.tool()
def list_raw_materials(plant_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    List all raw materials/products in inventory with their stage distribution.
    :param plant_id: Optional plant/branch ID filter
    :return: List of raw materials
    """
    return inventory_manager.list_raw_materials(plant_id=plant_id)


@mcp.tool()
def update_raw_material(
    material_id_or_name: str,
    new_name: Optional[str] = None,
    quantity: Optional[int] = None,
    quantity_metric: Optional[str] = None,
    usage: Optional[int] = None,
    usage_metric: Optional[str] = None
) -> str:
    """
    Update an existing raw material's name, quantity, or metric.
    :param material_id_or_name: Material ID or current name
    :param new_name: New name for the material
    :param quantity: Updated quantity
    :param quantity_metric: Updated quantity metric
    :param usage: Updated usage
    :param usage_metric: Updated usage metric
    :return: Confirmation message
    """
    return inventory_manager.update_raw_material(
        material_id_or_name=material_id_or_name,
        new_name=new_name,
        quantity=quantity,
        quantity_metric=quantity_metric,
        usage=usage,
        usage_metric=usage_metric
    )


@mcp.tool()
def delete_raw_material(material_id_or_name: str) -> str:
    """
    Delete a raw material and associated stock QR entries.
    :param material_id_or_name: ID or name of the raw material to delete
    :return: Confirmation message
    """
    return inventory_manager.delete_raw_material(material_id_or_name=material_id_or_name)


@mcp.tool()
def add_product_stock(
    qr_id: str,
    raw_material_name: str,
    stage_name: str = "Raw Material",
    cost: int = 100,
    plant_id: int = 1
) -> str:
    """
    Add a specific QR product stock item mapped to a raw material and stage.
    :param qr_id: Unique QR code / product serial string
    :param raw_material_name: Name of the raw material
    :param stage_name: Name of the stage (e.g., Raw Material, Processing, Cooking)
    :param cost: Unit cost
    :param plant_id: Plant ID
    :return: Confirmation message
    """
    return inventory_manager.add_product_stock(
        qr_id=qr_id,
        raw_material_name=raw_material_name,
        stage_name=stage_name,
        cost=cost,
        plant_id=plant_id
    )


@mcp.tool()
def shift_material_stage(
    material_name: str,
    target_stage_name: str,
    plant_id: int = 1,
    quantity_or_count: Optional[int] = None
) -> str:
    """
    Shift raw materials or product stocks from their current stage to a target stage using natural text commands.
    :param material_name: Name of the material or product (e.g., Paneer, Tomato, Steel Sheet)
    :param target_stage_name: Target stage (e.g. Processing, Cooking, Packaging, Quality Inspection, Storage Warehouse)
    :param plant_id: Plant ID (default 1)
    :param quantity_or_count: Number of stock units to move (if omitted, shifts all available items)
    :return: Confirmation message
    """
    return inventory_manager.shift_material_stage(
        material_name=material_name,
        target_stage_name=target_stage_name,
        plant_id=plant_id,
        quantity_or_count=quantity_or_count
    )


@mcp.tool()
def delete_product_stock(qr_id: str) -> str:
    """
    Delete a specific QR stock item by QR code ID.
    :param qr_id: Unique QR code identifier
    :return: Confirmation message
    """
    return inventory_manager.delete_product_stock(qr_id=qr_id)


@mcp.tool()
def get_inventory_stats(plant_id: Optional[int] = None) -> Dict[str, Any]:
    """
    Get comprehensive inventory breakdown including condition counts, expired items, and stage distribution.
    :param plant_id: Optional plant ID filter
    :return: Aggregated inventory statistics
    """
    return inventory_manager.get_inventory_stats(plant_id=plant_id)


@mcp.tool()
def list_products_and_stocks(
    plant_id: Optional[int] = None,
    stage_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    List all individual tracked QR stock items with details like stage, percent remaining, and condition.
    :param plant_id: Optional plant ID
    :param stage_name: Optional stage name filter (e.g., Processing, Cooking, Storage Warehouse)
    :return: List of stock items
    """
    return inventory_manager.list_products_and_stocks(plant_id=plant_id, stage_name=stage_name)


# ---------------------------------------------------------
# Stage Management Tools
# ---------------------------------------------------------

@mcp.tool()
def list_stages(plant_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    List all production and processing stages for a plant.
    :param plant_id: Optional plant ID
    :return: List of stages
    """
    return stage_manager.list_stages(plant_id=plant_id)


@mcp.tool()
def create_stage(stage_name: str, plant_id: int = 1) -> str:
    """
    Create a new production or inventory stage (e.g., Raw Material, Processing, Cooking, Packaging, Quality Check).
    :param stage_name: Name of the stage
    :param plant_id: Plant ID (default 1)
    :return: Confirmation message
    """
    return stage_manager.create_stage(stage_name=stage_name, plant_id=plant_id)


@mcp.tool()
def update_stage(stage_id_or_name: str, new_stage_name: str) -> str:
    """
    Rename an existing production or inventory stage.
    :param stage_id_or_name: ID or current name of the stage
    :param new_stage_name: New name for the stage
    :return: Confirmation message
    """
    return stage_manager.update_stage(stage_id_or_name=stage_id_or_name, new_stage_name=new_stage_name)


@mcp.tool()
def delete_stage(stage_id_or_name: str) -> str:
    """
    Delete a production stage from a plant.
    :param stage_id_or_name: ID or name of the stage
    :return: Confirmation message
    """
    return stage_manager.delete_stage(stage_id_or_name=stage_id_or_name)


# ---------------------------------------------------------
# Finished Products & BOM (Bill of Materials) Tools
# ---------------------------------------------------------

@mcp.tool()
def list_products_and_bom(plant_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    List finished products, prices, and Bill of Materials (BOM) ingredient breakdown.
    :param plant_id: Optional plant ID
    :return: List of products with BOM components
    """
    return product_manager.list_products_and_bom(plant_id=plant_id)


@mcp.tool()
def create_product_with_bom(
    name: str,
    price: float,
    components: Any
) -> str:
    """
    Create a new finished product with Bill of Materials (BOM) ingredient requirements.
    :param name: Product name (e.g. Cheese Pizza, Paneer Butter Masala)
    :param price: Price per unit
    :param components: List of raw material components or JSON string e.g. [{"raw_material_name": "Paneer", "usage": 200}]
    :return: Confirmation message
    """
    return product_manager.create_product_with_bom(name=name, price=price, components=components)


@mcp.tool()
def delete_product(product_id_or_name: str) -> str:
    """
    Delete a finished product by ID or name.
    :param product_id_or_name: ID or name of the product
    :return: Confirmation message
    """
    return product_manager.delete_product(product_id_or_name=product_id_or_name)


# ---------------------------------------------------------
# Factory Machinery & Condition Tools
# ---------------------------------------------------------

@mcp.tool()
def list_machines(plant_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    List all factory machines and their parameter boundaries.
    :param plant_id: Optional plant ID
    :return: List of machines
    """
    return machine_manager.list_machines(plant_id=plant_id)


@mcp.tool()
def add_machine(
    name: str,
    lower_bound: int,
    upper_bound: int,
    normal_level: int,
    metric: str = "Temperature",
    plant_id: int = 1
) -> str:
    """
    Add a new machine to monitor in a plant.
    :param name: Machine name (e.g. Oven A, Mixer 3)
    :param lower_bound: Minimum acceptable value
    :param upper_bound: Maximum acceptable value
    :param normal_level: Normal operating level
    :param metric: Measurement metric
    :param plant_id: Plant ID
    :return: Confirmation message
    """
    return machine_manager.add_machine(
        name=name,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        normal_level=normal_level,
        metric=metric,
        plant_id=plant_id
    )


@mcp.tool()
def record_machine_condition(machine_id: int, time_of_day: str, value: int) -> str:
    """
    Record machine condition reading for morning, afternoon, or evening.
    :param machine_id: ID of the machine
    :param time_of_day: 'morning', 'afternoon', or 'evening'
    :param value: Recorded value
    :return: Confirmation message
    """
    return machine_manager.record_machine_condition(machine_id=machine_id, time_of_day=time_of_day, value=value)


@mcp.tool()
def update_machine(
    machine_id_or_name: str,
    new_name: Optional[str] = None,
    lower_bound: Optional[int] = None,
    upper_bound: Optional[int] = None,
    normal_level: Optional[int] = None
) -> str:
    """
    Update details/bounds of a machine.
    :param machine_id_or_name: Machine ID or current name
    :param new_name: New machine name
    :param lower_bound: Min parameter threshold
    :param upper_bound: Max parameter threshold
    :param normal_level: Ideal parameter level
    :return: Confirmation message
    """
    return machine_manager.update_machine(
        machine_id_or_name=machine_id_or_name,
        new_name=new_name,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        normal_level=normal_level
    )


@mcp.tool()
def delete_machine(machine_id_or_name: str) -> str:
    """
    Delete a machine and its condition records.
    :param machine_id_or_name: ID or name of the machine
    :return: Confirmation message
    """
    return machine_manager.delete_machine(machine_id_or_name=machine_id_or_name)


# ---------------------------------------------------------
# Shifts & Scheduling Tools
# ---------------------------------------------------------

@mcp.tool()
def list_shifts(plant_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    List active shifts and timing schedules.
    :param plant_id: Optional plant ID
    :return: List of shift schedules
    """
    return shift_manager.list_shifts(plant_id=plant_id)


@mcp.tool()
def create_shift(
    name: str,
    start_time: str,
    end_time: str,
    day: str = "Monday",
    plant_id: int = 1
) -> str:
    """
    Create a new shift schedule.
    :param name: Name of the shift (e.g., Morning Shift, Night Shift)
    :param start_time: Start time in HH:MM format (e.g. 09:00)
    :param end_time: End time in HH:MM format (e.g. 17:00)
    :param day: Day of the week
    :param plant_id: Plant ID
    :return: Confirmation message
    """
    return shift_manager.create_shift(
        name=name,
        start_time=start_time,
        end_time=end_time,
        day=day,
        plant_id=plant_id
    )


@mcp.tool()
def update_shift(
    shift_id_or_name: str,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    day: Optional[str] = None
) -> str:
    """
    Update shift timing or day.
    :param shift_id_or_name: Shift ID or current name
    :param start_time: Updated start time (HH:MM)
    :param end_time: Updated end time (HH:MM)
    :param day: Updated day of week
    :return: Confirmation message
    """
    return shift_manager.update_shift(
        shift_id_or_name=shift_id_or_name,
        start_time=start_time,
        end_time=end_time,
        day=day
    )


@mcp.tool()
def delete_shift(shift_id_or_name: str) -> str:
    """
    Delete a shift schedule.
    :param shift_id_or_name: Shift ID or name
    :return: Confirmation message
    """
    return shift_manager.delete_shift(shift_id_or_name=shift_id_or_name)


# ---------------------------------------------------------
# Orders & Prediction Tools
# ---------------------------------------------------------

@mcp.tool()
def list_sales_orders(date_str: Optional[str] = None, plant_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    List historical sales/production orders and revenue.
    :param date_str: Optional date string in YYYY-MM-DD format
    :param plant_id: Optional plant ID
    :return: List of sales orders
    """
    return order_manager.list_sales_orders(date_str=date_str, plant_id=plant_id)


@mcp.tool()
def create_sales_order(items: Any, plant_id: int = 1) -> str:
    """
    Create a new sales/production order and automatically deduct ingredient stock.
    :param items: List of items or JSON string e.g. [{"product_name": "Paneer Pizza", "quantity": 2}]
    :param plant_id: Plant ID
    :return: Confirmation message
    """
    return order_manager.create_sales_order(items=items, plant_id=plant_id)


@mcp.tool()
def get_sales_prediction(days: int = 7, plant_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Get 7-day (or N-day) expected sales forecasting using ARIMA time-series analysis on historical order records.
    :param days: Number of days to forecast (default 7)
    :param plant_id: Optional plant ID
    :return: Predicted sales forecast per product
    """
    return order_manager.get_sales_prediction(days=days, plant_id=plant_id)


@mcp.tool()
def get_material_order_prediction(days: int = 7, plant_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Calculate predicted raw material demand based on ARIMA sales forecasts and BOM explosion, recommending boxes to purchase.
    :param days: Number of days ahead to forecast
    :param plant_id: Optional plant ID
    :return: List of predicted raw material requirements and recommended order quantities
    """
    return order_manager.get_material_order_prediction(days=days, plant_id=plant_id)


# ---------------------------------------------------------
# FastMCP Prompts
# ---------------------------------------------------------

@mcp.prompt("onboard_new_product")
def onboard_new_product(product_name: str, initial_quantity: int = 10, target_stage: str = "Raw Material"):
    return f"""Onboard a new product into the inventory system:
    - Product Name: {product_name}
    - Initial Quantity: {initial_quantity}
    - Target Stage: {target_stage}
    Steps to follow:
    1. Check if the raw material '{product_name}' already exists; if not, add it using `add_raw_material`.
    2. Ensure stage '{target_stage}' exists using `create_stage`.
    3. Register product stock item(s) mapped to stage '{target_stage}'.
    4. Provide a summary of the current inventory status.
    """


@mcp.prompt("shift_inventory_stage")
def shift_inventory_stage(product_name: str, target_stage: str):
    return f"""Shift inventory materials between stages:
    - Target Material: {product_name}
    - New Stage: {target_stage}
    Steps:
    1. Call `shift_material_stage` to update stock location to '{target_stage}'.
    2. Confirm total items moved and display remaining stage breakdown.
    """


@mcp.prompt("daily_inventory_audit")
def daily_inventory_audit():
    return """Perform a comprehensive daily inventory & machinery audit:
    1. Query overall stock statistics using `get_inventory_stats`.
    2. List machines using `list_machines` and check recent condition records.
    3. Summarize any low stock or expired inventory warnings.
    """


# Comprehensive list of all registered FastMCP domain tools
mcp_tools = [
    send_email,
    add_raw_material,
    get_raw_material_details,
    list_raw_materials,
    update_raw_material,
    delete_raw_material,
    add_product_stock,
    shift_material_stage,
    delete_product_stock,
    get_inventory_stats,
    list_products_and_stocks,
    list_stages,
    create_stage,
    update_stage,
    delete_stage,
    list_products_and_bom,
    create_product_with_bom,
    delete_product,
    list_machines,
    add_machine,
    record_machine_condition,
    update_machine,
    delete_machine,
    list_shifts,
    create_shift,
    update_shift,
    delete_shift,
    list_sales_orders,
    create_sales_order,
    get_sales_prediction,
    get_material_order_prediction
]

mcp_tool_map = {tool.__name__: tool for tool in mcp_tools}


if __name__ == "__main__":
    mcp.run(transport="stdio")

