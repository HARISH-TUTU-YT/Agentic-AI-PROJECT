import os
import sys
import math
from decimal import Decimal, ROUND_DOWN
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict

# Setup Django environment if not loaded
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'InventoryCore.settings')
os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"

import django
django.setup()

import pandas as pd
from statsmodels.tsa.arima.model import ARIMA

from factory.models import Factory, Plant, Machine, MachineConditionRecord, Shift
from inventory.models import RawMaterial, Stage, QRCode
from order.models import Product, BOMItem, ProductionOrder, ProductionOrderItem
from utils.choices import Choice
from utils.types import MetricType, ConditionType
from utils.helper import Helper


class InventoryManager:
    """Manager responsible for Raw Materials, QR Stock Items, and Stage Shifting."""

    def add_raw_material(
        self,
        name: str,
        quantity: int,
        quantity_metric: str = "Kilogram",
        usage: int = 1,
        usage_metric: str = "Kg",
        plant_id: int = 1
    ) -> str:
        plant = Plant.objects.filter(id=plant_id).first() or Plant.objects.first()
        if not plant:
            return "Error: No plants exist in database."

        q_metric = Helper.get_quantity_metric_no(quantity_metric) if quantity_metric in [c[1] for c in Choice.quantity_metric_choices] else 3
        u_metric = Helper.get_usage_metric_no(usage_metric) if usage_metric in [c[1] for c in Choice.usage_metric_choices] else 1

        rm, created = RawMaterial.objects.get_or_create(
            name=name,
            quantity=quantity,
            quantity_metric=q_metric,
            plant=plant,
            defaults={'usage': usage, 'usage_metric': u_metric}
        )
        status_str = "added successfully" if created else f"already exists (ID: {rm.id})"
        return f"Raw material '{name}' {status_str} with quantity {quantity} {quantity_metric} for plant '{plant.location}'."

    def get_raw_material_details(self, name: str, plant_id: Optional[int] = None) -> Dict[str, Any]:
        qs = RawMaterial.objects.filter(name__icontains=name)
        if plant_id:
            qs = qs.filter(plant_id=plant_id)
        if not qs.exists():
            return {"error": f"No raw materials found matching '{name}'."}

        rm = qs.first()
        stocks = QRCode.objects.filter(raw_material=rm)
        stages = list(stocks.values_list('stage__stage', flat=True).distinct())

        return {
            "id": rm.id,
            "name": rm.name,
            "quantity": rm.quantity,
            "quantity_metric": rm.get_quantity_metric_display(),
            "usage": rm.usage,
            "usage_metric": rm.get_usage_metric_display() if rm.usage_metric else None,
            "plant_id": rm.plant.id,
            "plant_location": rm.plant.location,
            "total_stock_qrs": stocks.count(),
            "active_stages": [s for s in stages if s]
        }

    def list_raw_materials(self, plant_id: Optional[int] = None) -> List[Dict[str, Any]]:
        qs = RawMaterial.objects.all()
        if plant_id and qs.filter(plant_id=plant_id).exists():
            qs = qs.filter(plant_id=plant_id)

        materials = []
        for rm in qs:
            stocks = QRCode.objects.filter(raw_material=rm)
            stage_dist = {}
            for s in stocks:
                s_name = s.stage.stage if s.stage else "Unassigned"
                stage_dist[s_name] = stage_dist.get(s_name, 0) + 1

            materials.append({
                "id": rm.id,
                "name": rm.name,
                "quantity": rm.quantity,
                "metric": rm.get_quantity_metric_display(),
                "plant": rm.plant.location,
                "total_qr_stocks": stocks.count(),
                "stage_distribution": stage_dist
            })
        return materials

    def update_raw_material(
        self,
        material_id_or_name: str,
        new_name: Optional[str] = None,
        quantity: Optional[int] = None,
        quantity_metric: Optional[str] = None,
        usage: Optional[int] = None,
        usage_metric: Optional[str] = None
    ) -> str:
        if str(material_id_or_name).isdigit():
            rms = RawMaterial.objects.filter(id=int(material_id_or_name))
        else:
            rms = RawMaterial.objects.filter(name__icontains=material_id_or_name)

        if not rms.exists():
            return f"Error: Raw material '{material_id_or_name}' not found."

        rm = rms.first()
        if new_name:
            rm.name = new_name
        if quantity is not None:
            rm.quantity = quantity
        if quantity_metric and quantity_metric in [c[1] for c in Choice.quantity_metric_choices]:
            rm.quantity_metric = Helper.get_quantity_metric_no(quantity_metric)
        if usage is not None:
            rm.usage = usage
        if usage_metric and usage_metric in [c[1] for c in Choice.usage_metric_choices]:
            rm.usage_metric = Helper.get_usage_metric_no(usage_metric)

        rm.save()
        return f"Raw material '{rm.name}' (ID: {rm.id}) updated successfully."

    def delete_raw_material(self, material_id_or_name: str) -> str:
        if str(material_id_or_name).isdigit():
            rms = RawMaterial.objects.filter(id=int(material_id_or_name))
        else:
            rms = RawMaterial.objects.filter(name__icontains=material_id_or_name)

        if not rms.exists():
            return f"Error: Raw material '{material_id_or_name}' not found."

        names = list(rms.values_list('name', flat=True))
        count = rms.count()
        rms.delete()
        return f"Successfully deleted {count} raw material(s): {', '.join(names)}."

    def add_product_stock(
        self,
        qr_id: str,
        raw_material_name: str,
        stage_name: str = "Raw Material",
        cost: int = 100,
        plant_id: int = 1
    ) -> str:
        plant = Plant.objects.filter(id=plant_id).first() or Plant.objects.first()
        if not plant:
            return "Error: No plant found."

        rm = RawMaterial.objects.filter(name__icontains=raw_material_name, plant=plant).first() or RawMaterial.objects.filter(name__icontains=raw_material_name).first()
        if not rm:
            return f"Error: Raw material '{raw_material_name}' not found. Please add the raw material first."

        stage, _ = Stage.objects.get_or_create(stage=stage_name, plant=plant)

        qr, _ = QRCode.objects.get_or_create(id=qr_id)
        qr.raw_material = rm
        qr.stage = stage
        qr.cost = cost
        qr.available_percent = 100
        qr.save()

        return f"Product stock '{qr_id}' mapped to '{rm.name}' in stage '{stage.stage}' successfully."

    def shift_material_stage(
        self,
        material_name: str,
        target_stage_name: str,
        plant_id: int = 1,
        quantity_or_count: Optional[int] = None
    ) -> str:
        plant = Plant.objects.filter(id=plant_id).first() or Plant.objects.first()
        if not plant:
            return "Error: Plant not found."

        rm = RawMaterial.objects.filter(name__icontains=material_name, plant=plant).first() or RawMaterial.objects.filter(name__icontains=material_name).first()
        if not rm:
            clean_name = material_name.strip()
            rm = RawMaterial.objects.create(
                name=clean_name,
                quantity=10,
                quantity_metric=3,
                plant=plant
            )

        target_stage, created = Stage.objects.get_or_create(stage=target_stage_name, plant=plant)
        stage_note = f" (Created new stage '{target_stage_name}')" if created else ""

        available_stocks = QRCode.objects.filter(raw_material=rm).exclude(stage=target_stage)

        if not available_stocks.exists():
            already_there = QRCode.objects.filter(raw_material=rm, stage=target_stage).count()
            if already_there > 0:
                return f"Notice: All {already_there} stock item(s) of '{rm.name}' are already in stage '{target_stage_name}'."
            # If no stock QRs exist at all, auto-generate initial stock item
            qr_id = f"{rm.name[:3].upper()}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            qr = QRCode.objects.create(
                id=qr_id,
                raw_material=rm,
                stage=target_stage,
                cost=100,
                available_percent=100
            )
            return f"Created stock item '{qr.id}' for '{rm.name}' directly in stage '{target_stage_name}'{stage_note}."

        if quantity_or_count and quantity_or_count > 0:
            stocks_to_move = list(available_stocks[:quantity_or_count])
        else:
            stocks_to_move = list(available_stocks)

        count = len(stocks_to_move)
        for stock in stocks_to_move:
            stock.stage = target_stage
            stock.save()

        return f"Successfully shifted {count} stock item(s) of '{rm.name}' to stage '{target_stage_name}'{stage_note}."

    def delete_product_stock(self, qr_id: str) -> str:
        qrs = QRCode.objects.filter(id=qr_id)
        if not qrs.exists():
            return f"Error: Stock QR item '{qr_id}' not found."
        qrs.delete()
        return f"Stock QR item '{qr_id}' deleted successfully."

    def get_inventory_stats(self, plant_id: Optional[int] = None) -> Dict[str, Any]:
        qs = QRCode.objects.filter(raw_material__isnull=False)
        if plant_id:
            qs = qs.filter(raw_material__plant_id=plant_id)

        total_stock = qs.count()
        good_condition = qs.filter(condition=ConditionType.GOOD).count()
        expired = qs.filter(condition=ConditionType.EXPIRED).count()
        partially_used = qs.filter(available_percent__lt=100, available_percent__gt=0).count()

        stage_breakdown = {}
        for s in qs:
            stage_name = s.stage.stage if s.stage else "Unassigned"
            stage_breakdown[stage_name] = stage_breakdown.get(stage_name, 0) + 1

        return {
            "total_stock_items": total_stock,
            "good_condition_count": good_condition,
            "expired_condition_count": expired,
            "partially_used_count": partially_used,
            "stage_breakdown": stage_breakdown
        }

    def list_products_and_stocks(
        self,
        plant_id: Optional[int] = None,
        stage_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        qs = QRCode.objects.filter(raw_material__isnull=False)
        if plant_id:
            qs = qs.filter(raw_material__plant_id=plant_id)
        if stage_name:
            qs = qs.filter(stage__stage__icontains=stage_name)

        stocks = []
        for s in qs:
            stocks.append({
                "qr_id": s.id,
                "material_name": s.raw_material.name if s.raw_material else None,
                "stage": s.stage.stage if s.stage else None,
                "available_percent": float(s.available_percent) if s.available_percent is not None else 100.0,
                "cost": s.cost,
                "plant": s.raw_material.plant.location if s.raw_material else None,
                "condition": s.get_condition_display() if s.condition else "Normal",
                "last_scanned": s.last_scanned_at.strftime("%Y-%m-%d %H:%M") if s.last_scanned_at else None
            })
        return stocks


class StageManager:
    """Manager responsible for Production and Warehouse Stages."""

    def list_stages(self, plant_id: Optional[int] = None) -> List[Dict[str, Any]]:
        qs = Stage.objects.all()
        if plant_id:
            qs = qs.filter(plant_id=plant_id)
        return [
            {"id": s.id, "stage": s.stage, "plant_id": s.plant.id, "plant_location": s.plant.location}
            for s in qs
        ]

    def create_stage(self, stage_name: str, plant_id: int = 1) -> str:
        plant = Plant.objects.filter(id=plant_id).first() or Plant.objects.first()
        if not plant:
            return "Error: No plants exist."

        stage, created = Stage.objects.get_or_create(stage=stage_name, plant=plant)
        action = "created successfully" if created else "already exists"
        return f"Stage '{stage_name}' (ID: {stage.id}) {action} for plant '{plant.location}'."

    def update_stage(self, stage_id_or_name: str, new_stage_name: str) -> str:
        if str(stage_id_or_name).isdigit():
            stages = Stage.objects.filter(id=int(stage_id_or_name))
        else:
            stages = Stage.objects.filter(stage__icontains=stage_id_or_name)

        if not stages.exists():
            return f"Error: Stage '{stage_id_or_name}' not found."

        s = stages.first()
        old_name = s.stage
        s.stage = new_stage_name
        s.save()
        return f"Stage '{old_name}' renamed to '{new_stage_name}' successfully."

    def delete_stage(self, stage_id_or_name: str) -> str:
        if str(stage_id_or_name).isdigit():
            stages = Stage.objects.filter(id=int(stage_id_or_name))
        else:
            stages = Stage.objects.filter(stage__icontains=stage_id_or_name)

        if not stages.exists():
            return f"Error: Stage '{stage_id_or_name}' not found."

        count = stages.count()
        names = list(stages.values_list('stage', flat=True))
        stages.delete()
        return f"Successfully deleted {count} stage(s): {', '.join(names)}."


class ProductManager:
    """Manager responsible for Finished Products and Bills of Materials (BOM)."""

    def list_products_and_bom(self, plant_id: Optional[int] = None) -> List[Dict[str, Any]]:
        qs = Product.objects.filter(is_deleted=False)
        if plant_id:
            qs = qs.filter(components__raw_material__plant_id=plant_id).distinct()

        res = []
        for p in qs:
            comps = []
            for c in p.components.all():
                comps.append({
                    "raw_material_id": c.raw_material.id,
                    "raw_material_name": c.raw_material.name,
                    "usage": c.usage,
                    "usage_metric": c.raw_material.get_usage_metric_display() if c.raw_material.usage_metric else "Unit"
                })
            res.append({
                "product_id": p.id,
                "product_name": p.name,
                "price": float(p.price),
                "bom_components": comps
            })
        return res

    def create_product_with_bom(
        self,
        name: str,
        price: float,
        components: Any
    ) -> str:
        import json
        prod, _ = Product.objects.get_or_create(name=name, defaults={'price': price})
        prod.price = price
        prod.is_deleted = False

        if isinstance(components, str):
            try:
                comp_list = json.loads(components)
            except Exception:
                comp_list = []
        elif isinstance(components, list):
            comp_list = components
        else:
            comp_list = []

        bom_items = []
        for comp in comp_list:
            if isinstance(comp, dict):
                rm_name = comp.get('raw_material_name') or comp.get('name')
                usage = int(comp.get('usage', 1))
            else:
                rm_name = str(comp)
                usage = 1

            rm = RawMaterial.objects.filter(name__icontains=rm_name).first()
            if rm:
                bom, _ = BOMItem.objects.get_or_create(raw_material=rm, usage=usage)
                bom_items.append(bom)

        prod.components.set(bom_items)
        prod.save()
        return f"Product '{prod.name}' (Price: ${price:.2f}) created with {len(bom_items)} BOM component(s)."

    def delete_product(self, product_id_or_name: str) -> str:
        if str(product_id_or_name).isdigit():
            products = Product.objects.filter(id=int(product_id_or_name))
        else:
            products = Product.objects.filter(name__icontains=product_id_or_name)

        if not products.exists():
            return f"Error: Product '{product_id_or_name}' not found."

        names = list(products.values_list('name', flat=True))
        for p in products:
            p.delete()
        return f"Successfully deleted product(s): {', '.join(names)}."


class MachineManager:
    """Manager responsible for Factory Machinery, Boundaries, and Condition Logs."""

    def list_machines(self, plant_id: Optional[int] = None) -> List[Dict[str, Any]]:
        qs = Machine.objects.all()
        if plant_id:
            qs = qs.filter(plant_id=plant_id)
        return [
            {
                "id": m.id,
                "name": m.name,
                "plant_id": m.plant.id,
                "normal_level": m.normal_level,
                "lower_bound": m.lower_bound,
                "upper_bound": m.upper_bound
            }
            for m in qs
        ]

    def add_machine(
        self,
        name: str,
        lower_bound: int,
        upper_bound: int,
        normal_level: int,
        metric: str = "Temperature",
        plant_id: int = 1
    ) -> str:
        plant = Plant.objects.filter(id=plant_id).first() or Plant.objects.first()
        if not plant:
            return "Error: No plant found."

        m = Machine.objects.create(
            name=name,
            plant=plant,
            lower_bound=lower_bound,
            upper_bound=upper_bound,
            normal_level=normal_level,
            metric=1
        )
        return f"Machine '{m.name}' added with normal level {normal_level} (Bounds: {lower_bound} - {upper_bound})."

    def record_machine_condition(self, machine_id: int, time_of_day: str, value: int) -> str:
        try:
            m = Machine.objects.get(id=machine_id)
        except Machine.DoesNotExist:
            return f"Error: Machine with ID {machine_id} not found."

        rec, _ = MachineConditionRecord.objects.get_or_create(machine=m, recorded_on=date.today())
        tod = time_of_day.lower()
        if tod == 'morning':
            rec.morning_value = value
        elif tod == 'afternoon':
            rec.afternoon_value = value
        elif tod == 'evening':
            rec.evening_value = value
        else:
            return "Invalid time_of_day. Use 'morning', 'afternoon', or 'evening'."
        rec.save()
        return f"Condition recorded for Machine '{m.name}': {time_of_day} = {value}."

    def update_machine(
        self,
        machine_id_or_name: str,
        new_name: Optional[str] = None,
        lower_bound: Optional[int] = None,
        upper_bound: Optional[int] = None,
        normal_level: Optional[int] = None
    ) -> str:
        if str(machine_id_or_name).isdigit():
            machines = Machine.objects.filter(id=int(machine_id_or_name))
        else:
            machines = Machine.objects.filter(name__icontains=machine_id_or_name)

        if not machines.exists():
            return f"Error: Machine '{machine_id_or_name}' not found."

        m = machines.first()
        if new_name:
            m.name = new_name
        if lower_bound is not None:
            m.lower_bound = lower_bound
        if upper_bound is not None:
            m.upper_bound = upper_bound
        if normal_level is not None:
            m.normal_level = normal_level

        m.save()
        return f"Machine '{m.name}' (ID: {m.id}) updated successfully."

    def delete_machine(self, machine_id_or_name: str) -> str:
        if str(machine_id_or_name).isdigit():
            machines = Machine.objects.filter(id=int(machine_id_or_name))
        else:
            machines = Machine.objects.filter(name__icontains=machine_id_or_name)

        if not machines.exists():
            return f"Error: Machine '{machine_id_or_name}' not found."

        count = machines.count()
        names = list(machines.values_list('name', flat=True))
        machines.delete()
        return f"Successfully deleted {count} machine(s): {', '.join(names)}."


class ShiftManager:
    """Manager responsible for Work Shifts and Worker Scheduling."""

    def list_shifts(self, plant_id: Optional[int] = None) -> List[Dict[str, Any]]:
        qs = Shift.objects.all()
        if plant_id:
            qs = qs.filter(plant_id=plant_id)
        return [
            {
                "id": s.id,
                "name": s.name,
                "day": s.get_day_display(),
                "start_time": s.start_time.strftime("%H:%M"),
                "end_time": s.end_time.strftime("%H:%M"),
                "plant_id": s.plant.id
            }
            for s in qs
        ]

    def create_shift(
        self,
        name: str,
        start_time: str,
        end_time: str,
        day: str = "Monday",
        plant_id: int = 1
    ) -> str:
        plant = Plant.objects.filter(id=plant_id).first() or Plant.objects.first()
        if not plant:
            return "Error: No plant found."

        day_no = Helper.get_day_no(day) if day in [c[1] for c in Choice.day_choices] else 1
        st = datetime.strptime(start_time, "%H:%M").time()
        et = datetime.strptime(end_time, "%H:%M").time()

        s, created = Shift.objects.get_or_create(
            name=name,
            day=day_no,
            start_time=st,
            end_time=et,
            plant=plant
        )
        action = "created successfully" if created else "already exists"
        return f"Shift '{s.name}' ({start_time}-{end_time}) on {day} {action}."

    def update_shift(
        self,
        shift_id_or_name: str,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        day: Optional[str] = None
    ) -> str:
        if str(shift_id_or_name).isdigit():
            shifts = Shift.objects.filter(id=int(shift_id_or_name))
        else:
            shifts = Shift.objects.filter(name__icontains=shift_id_or_name)

        if not shifts.exists():
            return f"Error: Shift '{shift_id_or_name}' not found."

        s = shifts.first()
        if start_time:
            s.start_time = datetime.strptime(start_time, "%H:%M").time()
        if end_time:
            s.end_time = datetime.strptime(end_time, "%H:%M").time()
        if day and day in [c[1] for c in Choice.day_choices]:
            s.day = Helper.get_day_no(day)

        s.save()
        return f"Shift '{s.name}' updated successfully."

    def delete_shift(self, shift_id_or_name: str) -> str:
        if str(shift_id_or_name).isdigit():
            shifts = Shift.objects.filter(id=int(shift_id_or_name))
        else:
            shifts = Shift.objects.filter(name__icontains=shift_id_or_name)

        if not shifts.exists():
            return f"Error: Shift '{shift_id_or_name}' not found."

        count = shifts.count()
        names = list(shifts.values_list('name', flat=True))
        shifts.delete()
        return f"Successfully deleted {count} shift(s): {', '.join(names)}."


class OrderManager:
    """Manager responsible for Orders, Stock Deductions, and ARIMA Demand Predictions."""

    def list_sales_orders(self, date_str: Optional[str] = None, plant_id: Optional[int] = None) -> List[Dict[str, Any]]:
        qs = ProductionOrder.objects.all()
        if plant_id:
            qs = qs.filter(plant_id=plant_id)
        if date_str:
            try:
                d = datetime.strptime(date_str, "%Y-%m-%d").date()
                qs = qs.filter(ordered_at__date=d)
            except ValueError:
                pass

        orders = []
        for o in qs.order_by('-ordered_at')[:50]:
            items = []
            for item in o.order_items.all():
                items.append({
                    "product_name": item.product.name,
                    "quantity": item.quantity,
                    "price_per_unit": float(item.product.price),
                    "total_price": float(item.product.price * item.quantity)
                })
            orders.append({
                "order_id": o.id,
                "ordered_at": o.ordered_at.strftime("%Y-%m-%d %H:%M"),
                "plant_id": o.plant.id,
                "total_order_cost": float(o.total_cost()),
                "items": items
            })
        return orders

    def create_sales_order(self, items: Any, plant_id: int = 1) -> str:
        import json
        plant = Plant.objects.filter(id=plant_id).first() or Plant.objects.first()
        if not plant:
            return "Error: No plant found."

        if isinstance(items, str):
            try:
                item_list = json.loads(items)
            except Exception:
                item_list = [{"product_name": items, "quantity": 1}]
        elif isinstance(items, list):
            item_list = items
        else:
            item_list = [items]

        order = ProductionOrder.objects.create(plant=plant)
        created_items = []
        for it in item_list:
            if isinstance(it, dict):
                p_name = it.get('product_name') or it.get('name')
                qty = int(it.get('quantity', 1))
            else:
                p_name = str(it)
                qty = 1

            prod = Product.objects.filter(name__icontains=p_name, is_deleted=False).first()
            if not prod:
                continue
            ProductionOrderItem.objects.create(order=order, product=prod, quantity=qty)
            created_items.append(f"{qty}x {prod.name}")

        if not created_items:
            order.delete()
            return "Error: No matching products found for order creation."

        return f"Sales Order #{order.id} created successfully for plant '{plant.location}' with items: {', '.join(created_items)}. Total: ${order.total_cost():.2f}"

    def get_sales_prediction(self, days: int = 7, plant_id: Optional[int] = None) -> List[Dict[str, Any]]:
        days = int(days)
        products = Product.objects.filter(is_deleted=False)
        if plant_id:
            products = products.filter(components__raw_material__plant__id=plant_id).distinct()

        predictions = []
        for product in products:
            order_items = ProductionOrderItem.objects.filter(product=product).order_by('order__ordered_at')
            data = []
            for item in order_items:
                data.append({'date': item.order.ordered_at.date(), 'sales': item.quantity})

            if len(data) >= 3:
                df = pd.DataFrame(data)
                df = df.groupby('date').agg({'sales': 'sum'}).reset_index()
                df.set_index('date', inplace=True)
                df = df.asfreq('D', fill_value=0)
                try:
                    model = ARIMA(df['sales'], order=(1, 1, 1))
                    model_fit = model.fit()
                    forecast = model_fit.forecast(steps=days)
                    predicted_sales = [max(0, int(round(val))) for val in forecast]
                except Exception:
                    avg_sale = max(1, int(round(df['sales'].mean())))
                    predicted_sales = [avg_sale] * days
            else:
                predicted_sales = [5] * days

            start_date = date.today() + timedelta(days=1)
            forecast_data = [
                {'date': (start_date + timedelta(days=i)).strftime('%Y-%m-%d'), 'predicted_quantity': qty}
                for i, qty in enumerate(predicted_sales)
            ]
            predictions.append({
                "product_id": product.id,
                "product_name": product.name,
                "total_predicted_sales": sum(predicted_sales),
                "forecast": forecast_data
            })
        return predictions

    def get_material_order_prediction(self, days: int = 7, plant_id: Optional[int] = None) -> List[Dict[str, Any]]:
        raw_materials = RawMaterial.objects.all()
        if plant_id:
            raw_materials = raw_materials.filter(plant_id=plant_id)

        sales_preds = self.get_sales_prediction(days=days, plant_id=plant_id)
        sales_map = {p['product_id']: p['total_predicted_sales'] for p in sales_preds}

        material_usage = defaultdict(int)
        for prod_id, total_sales in sales_map.items():
            prod = Product.objects.filter(id=prod_id).first()
            if not prod:
                continue
            for comp in prod.components.all():
                material_usage[comp.raw_material.id] += comp.usage * total_sales

        order_predictions = []
        for raw_material in raw_materials:
            count = material_usage.get(raw_material.id, 0)
            one_box = Decimal(str(raw_material.quantity)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)

            if raw_material.usage_metric == MetricType.GRAM and raw_material.quantity_metric == MetricType.KG:
                one_box = one_box * 1000
            elif raw_material.usage_metric == MetricType.ML and raw_material.quantity_metric == MetricType.LTR:
                one_box = one_box * 1000
            elif raw_material.usage_metric == MetricType.PIECE and raw_material.usage:
                one_box = one_box * raw_material.usage

            if float(one_box) == 0:
                continue

            in_stock = Decimal('0.0')
            for stock in QRCode.objects.filter(raw_material=raw_material, available_percent__gt=0).exclude(condition=ConditionType.EXPIRED):
                stock_q = Decimal(str(raw_material.quantity)).quantize(Decimal('0.01'), rounding=ROUND_DOWN)
                if raw_material.usage_metric == MetricType.GRAM and raw_material.quantity_metric == MetricType.KG:
                    stock_q = stock_q * 1000
                elif raw_material.usage_metric == MetricType.ML and raw_material.quantity_metric == MetricType.LTR:
                    stock_q = stock_q * 1000
                elif raw_material.usage_metric == MetricType.PIECE and raw_material.usage:
                    stock_q = stock_q * raw_material.usage
                stock_q = (Decimal(str(stock.available_percent)) / Decimal('100')) * stock_q
                in_stock += stock_q

            predicted_boxes = (Decimal(str(count)) / one_box) * Decimal('1.05')
            if raw_material.usage_metric == MetricType.PIECE and raw_material.usage:
                predicted_boxes = math.ceil(float(predicted_boxes) / raw_material.usage)
            else:
                predicted_boxes = math.ceil(float(predicted_boxes))

            required_boxes = 0
            rem_count = Decimal(str(count))
            if in_stock < rem_count:
                rem_count -= in_stock
                req_b = (rem_count / one_box) * Decimal('1.05')
                if raw_material.usage_metric == MetricType.PIECE and raw_material.usage:
                    required_boxes = math.ceil(float(req_b) / raw_material.usage)
                else:
                    required_boxes = math.ceil(float(req_b))

            order_predictions.append({
                "raw_material_id": raw_material.id,
                "raw_material_name": raw_material.name,
                "forecast_days": days,
                "predicted_demand": int(count),
                "current_in_stock": float(in_stock),
                "predicted_boxes": predicted_boxes,
                "required_boxes": required_boxes
            })

        return order_predictions


def seed_services(
    inventory_manager: InventoryManager,
    stage_manager: StageManager,
    product_manager: ProductManager,
    machine_manager: MachineManager,
    shift_manager: ShiftManager,
    order_manager: OrderManager
) -> None:
    """Ensure baseline plants, default stages, and primary configurations exist."""
    # Ensure default factory and plant exist
    factory = Factory.objects.first()
    if not factory:
        factory = Factory.objects.create(name="Dine Central Kitchen")

    plant = Plant.objects.first()
    if not plant:
        plant = Plant.objects.create(
            factory=factory,
            location="Main Facility",
            address="100 Industrial Area"
        )

    # Core stages required for production pipeline
    core_stages = [
        "Raw Material",
        "Storage Warehouse",
        "Production Floor",
        "Processing",
        "Cooking",
        "Quality Inspection",
        "Packaging"
    ]
    for stage_name in core_stages:
        Stage.objects.get_or_create(stage=stage_name, plant=plant)
