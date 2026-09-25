import re
import json
from typing import Dict, Any, Optional
import mcp_server


class MCPAgentDispatcher:
    """
    Intelligent Agentic Dispatcher that bridges natural language queries
    from the frontend chat directly to FastMCP domain tools.
    Zero external API quota dependency, fast, robust, and reliable.
    """

    @classmethod
    def dispatch(cls, query: str, plant_id: Optional[int] = 1) -> str:
        q = (query or "").strip()
        if not q:
            return "Please provide a query or command."

        q_lower = q.lower()

        # -------------------------------------------------------------
        # 1. SHIFT MATERIAL STAGE
        # -------------------------------------------------------------
        # Examples:
        # "Shift 1 stock item of Silicon Wafer to Quality Inspection stage"
        # "Move 2 Paneer to Cooking stage"
        # "Transfer Silicon Wafer to Storage Warehouse"
        # "Shift Paneer to Cooking"
        if any(verb in q_lower for verb in ["shift", "move", "transfer"]):
            shift_pattern = re.search(
                r'(?:shift|move|transfer)\s+(?:(\d+)\s*(?:stock|item|items|units?|piece|pieces)?\s*(?:of\s+)?)?(.+?)\s+(?:from\s+.+?\s+)?(?:back\s+)?to\s+([a-zA-Z0-9\s\-_]+?)(?:\s+stage|\.|\?|$)',
                q,
                re.IGNORECASE
            )
            if shift_pattern:
                qty_str = shift_pattern.group(1)
                qty = int(qty_str) if qty_str else None
                mat_name = shift_pattern.group(2).strip()
                # Clean filler words
                mat_name = re.sub(r'^(?:stock item of|item of|stock of|a |the )\s*', '', mat_name, flags=re.IGNORECASE).strip()
                target_stage = shift_pattern.group(3).strip()
                target_stage = re.sub(r'\s+stage$', '', target_stage, flags=re.IGNORECASE).strip()

                if mat_name and target_stage:
                    res = mcp_server.shift_material_stage(
                        material_name=mat_name,
                        target_stage_name=target_stage,
                        plant_id=plant_id,
                        quantity_or_count=qty
                    )
                    return (
                        f"### Material Stage Transfer\n\n"
                        f"- **Material**: `{mat_name}`\n"
                        f"- **Target Stage**: `{target_stage}`\n"
                        f"- **Quantity**: `{qty if qty else 'All available'}`\n\n"
                        f"**Status**: {res}"
                    )

        # -------------------------------------------------------------
        # 2. LIST RAW MATERIALS & STAGE BREAKDOWN
        # -------------------------------------------------------------
        if any(k in q_lower for k in [
            "list raw material", "list raw materials", "show raw material", 
            "raw materials currently in stock", "raw materials in stock", 
            "list materials", "show materials", "stage breakdown", "raw material stock"
        ]):
            materials = mcp_server.list_raw_materials(plant_id=plant_id)
            if not materials:
                return "No raw materials found in inventory for this plant."

            rows = []
            for m in materials:
                stage_str = ", ".join([f"{stg}: {cnt}" for stg, cnt in m.get("stage_distribution", {}).items()]) or "No active QR stocks"
                rows.append(f"| **{m.get('name')}** | {m.get('quantity')} {m.get('metric')} | {m.get('total_qr_stocks')} | {stage_str} |")

            table_content = "\n".join(rows)
            return (
                f"### Raw Materials & Stage Distribution\n\n"
                f"Found **{len(materials)}** raw material(s) in inventory:\n\n"
                f"| Material | Quantity | QR Stocks | Current Stage Breakdown |\n"
                f"| :--- | :--- | :--- | :--- |\n"
                f"{table_content}"
            )

        # -------------------------------------------------------------
        # 3. CREATE / ONBOARD FINISHED PRODUCT WITH BOM
        # -------------------------------------------------------------
        # Example: "Create a product named Margherita Pizza with price 12.99 and BOM components: Paneer 200g"
        if any(k in q_lower for k in ["create a product", "create product", "add product", "onboard product", "new product"]):
            name_match = re.search(r'named\s+([^,]+?)(?:\s+with|\s+price|\s+and|\s+having|\s+cost|\s*$)', q, re.IGNORECASE)
            price_match = re.search(r'price[:\s]+\$?([0-9]+(?:\.[0-9]+)?)', q, re.IGNORECASE)
            bom_match = re.search(r'(?:bom components?|components?|recipe|ingredients?)[:\s]+(.+)', q, re.IGNORECASE)

            prod_name = name_match.group(1).strip() if name_match else "Custom Finished Product"
            price = float(price_match.group(1)) if price_match else 15.0
            bom_raw = bom_match.group(1).strip() if bom_match else "Paneer 100"

            # Parse BOM components
            components = []
            for item in bom_raw.split(','):
                item = item.strip()
                if not item:
                    continue
                c_match = re.search(r'([a-zA-Z\s]+?)\s*(\d+)', item)
                if c_match:
                    components.append({"raw_material_name": c_match.group(1).strip(), "usage": int(c_match.group(2))})
                else:
                    components.append({"raw_material_name": item, "usage": 1})

            res = mcp_server.create_product_with_bom(
                name=prod_name,
                price=price,
                components=components
            )
            return (
                f"### Finished Product Registered\n\n"
                f"- **Product**: `{prod_name}`\n"
                f"- **Price**: `${price:.2f}`\n"
                f"- **Recipe (BOM)**: `{components}`\n\n"
                f"**Confirmation**: {res}"
            )

        # -------------------------------------------------------------
        # 4. LIST FINISHED PRODUCTS / PROJECTS & BOM
        # -------------------------------------------------------------
        if any(k in q_lower for k in [
            "list products", "list product", "show products", "show product",
            "list finished products", "projects", "list projects", "show projects",
            "bill of materials", "bom components", "product recipes"
        ]):
            prods = mcp_server.list_products_and_bom(plant_id=plant_id)
            if not prods:
                return "No finished products registered yet. You can create one using: `Create a product named [Name] with price [Price] and BOM components: [Ingredient] [Quantity]`."

            rows = []
            for p in prods:
                bom_items = p.get("bom_components", [])
                bom_desc = ", ".join([f"{b.get('raw_material_name')} ({b.get('usage')}{b.get('usage_metric')})" for b in bom_items]) or "None"
                rows.append(f"| **{p.get('product_name')}** | ${p.get('price'):.2f} | {bom_desc} |")

            table_content = "\n".join(rows)
            return (
                f"### Registered Finished Products & BOM\n\n"
                f"| Product Name | Unit Price | Bill of Materials (BOM) |\n"
                f"| :--- | :--- | :--- |\n"
                f"{table_content}"
            )

        # -------------------------------------------------------------
        # 5. ADD RAW MATERIAL
        # -------------------------------------------------------------
        if any(k in q_lower for k in ["add raw material", "create raw material", "new raw material"]):
            name_match = re.search(r'(?:add raw material|create raw material|new raw material)\s+([^,0-9]+?)(?:\s+with|\s+quantity|\s+qty|\s*$)', q, re.IGNORECASE)
            qty_match = re.search(r'(?:quantity|qty)[:\s]+(\d+)', q, re.IGNORECASE)
            metric_match = re.search(r'(kg|kilogram|gram|ltr|ml|unit)', q, re.IGNORECASE)

            name = name_match.group(1).strip() if name_match else "Ingredient"
            qty = int(qty_match.group(1)) if qty_match else 20
            metric = metric_match.group(1).capitalize() if metric_match else "Kilogram"

            res = mcp_server.add_raw_material(name=name, quantity=qty, quantity_metric=metric, plant_id=plant_id)
            return f"### Raw Material Added\n\n{res}"

        # -------------------------------------------------------------
        # 6. LIST OR CREATE STAGES
        # -------------------------------------------------------------
        if any(k in q_lower for k in ["list stages", "list stage", "show stages", "stages in pipeline"]):
            stages = mcp_server.list_stages(plant_id=plant_id)
            stage_list = "\n".join([f"- **Stage {s.get('id')}**: `{s.get('stage')}` ({s.get('plant_location')})" for s in stages])
            return f"### Production & Pipeline Stages\n\n{stage_list}"

        if any(k in q_lower for k in ["create stage", "add stage", "new stage"]):
            stage_match = re.search(r'(?:create stage|add stage|new stage)\s+(?:named\s+)?([a-zA-Z0-9\s\-_]+)', q, re.IGNORECASE)
            stage_name = stage_match.group(1).strip() if stage_match else "New Stage"
            res = mcp_server.create_stage(stage_name=stage_name, plant_id=plant_id)
            return f"### Stage Management\n\n{res}"

        # -------------------------------------------------------------
        # 7. MACHINERY & PARAMETER BOUNDARIES
        # -------------------------------------------------------------
        if any(k in q_lower for k in [
            "machine", "machinery", "parameter boundaries", "floor machines", "machine condition"
        ]):
            machines = mcp_server.list_machines(plant_id=plant_id)
            if not machines:
                return "No machines currently configured for this plant."

            rows = []
            for m in machines:
                rows.append(f"| **{m.get('name')}** | {m.get('normal_level')} | {m.get('lower_bound')} - {m.get('upper_bound')} | Normal |")

            table_content = "\n".join(rows)
            return (
                f"### Factory Machinery & Parameter Boundaries\n\n"
                f"| Machine Name | Normal Operating Level | Safe Parameter Bounds | Status |\n"
                f"| :--- | :--- | :--- | :--- |\n"
                f"{table_content}"
            )

        # -------------------------------------------------------------
        # 8. SALES FORECASTING & MATERIAL PREDICTION (ARIMA)
        # -------------------------------------------------------------
        if any(k in q_lower for k in ["forecast", "prediction", "predict", "arima"]):
            if "material" in q_lower:
                preds = mcp_server.get_material_order_prediction(days=7, plant_id=plant_id)
                if not preds:
                    return "Insufficient historical data to generate ARIMA material order predictions."
                rows = [f"| **{p.get('raw_material_name')}** | {p.get('predicted_demand')} | {p.get('current_in_stock')} | {p.get('required_boxes')} boxes |" for p in preds]
                table_content = "\n".join(rows)
                return (
                    f"### 7-Day ARIMA Raw Material Demand Forecast\n\n"
                    f"| Material | Predicted Demand | In Stock | Recommended Purchase |\n"
                    f"| :--- | :--- | :--- | :--- |\n"
                    f"{table_content}"
                )
            else:
                preds = mcp_server.get_sales_prediction(days=7, plant_id=plant_id)
                if not preds:
                    return "Insufficient sales order history to run 7-day ARIMA forecasting."
                rows = []
                for p in preds:
                    rev = p.get('expected_revenue')
                    rev_str = f"${rev:.2f}" if (rev is not None and isinstance(rev, (int, float))) else "N/A"
                    units = p.get('predicted_units', 0)
                    rows.append(f"| **{p.get('product_name')}** | {units} units | {rev_str} |")
                table_content = "\n".join(rows)
                return (
                    f"### 7-Day ARIMA Expected Sales Forecast\n\n"
                    f"| Product | Predicted Units | Expected Revenue |\n"
                    f"| :--- | :--- | :--- |\n"
                    f"{table_content}"
                )


        # -------------------------------------------------------------
        # 9. INVENTORY AUDIT & STATS
        # -------------------------------------------------------------
        if any(k in q_lower for k in ["stat", "audit", "summary", "overview"]):
            stats = mcp_server.get_inventory_stats(plant_id=plant_id)
            breakdown = stats.get("stage_breakdown", {})
            stg_rows = "\n".join([f"- **{k}**: {v} stock item(s)" for k, v in breakdown.items()]) or "None"
            return (
                f"### Dine Inventory Overview\n\n"
                f"- **Total Tracked QR Items**: `{stats.get('total_stock_items', 0)}`\n"
                f"- **Good Condition**: `{stats.get('good_condition_count', 0)}`\n"
                f"- **Expired Items**: `{stats.get('expired_condition_count', 0)}`\n"
                f"- **Partially Used**: `{stats.get('partially_used_count', 0)}`\n\n"
                f"**Stage Distribution Breakdown:**\n{stg_rows}"
            )

        # -------------------------------------------------------------
        # 10. LIST SHIFTS
        # -------------------------------------------------------------
        if "shift" in q_lower and any(w in q_lower for w in ["list", "show", "schedule", "timings"]):
            shifts = mcp_server.list_shifts(plant_id=plant_id)
            if not shifts:
                return "No shifts currently scheduled."
            rows = [f"| **{s.get('name')}** | {s.get('day')} | {s.get('start_time')} - {s.get('end_time')} |" for s in shifts]
            table_content = "\n".join(rows)
            return (
                f"### Active Work Shifts\n\n"
                f"| Shift Name | Day | Working Hours |\n"
                f"| :--- | :--- | :--- |\n"
                f"{table_content}"
            )

        # -------------------------------------------------------------
        # 11. GREETINGS & INTERACTIVE HELP
        # -------------------------------------------------------------
        return (
            f"**Hello! I am your Dine MCP-Powered Agentic AI Assistant.**\n\n"
            f"I have direct access to your factory & inventory MCP domain tools. Here are things you can ask me to do:\n\n"
            f"1. **Shift Material Stages**:\n"
            f"   - *\"Shift 1 stock item of Silicon Wafer to Quality Inspection stage\"*\n"
            f"   - *\"Move Silicon Wafer back to Storage Warehouse stage\"*\n\n"
            f"2. **Raw Materials & Inventory**:\n"
            f"   - *\"List all raw materials currently in stock and show their stage breakdown\"*\n"
            f"   - *\"Add raw material Tomato with quantity 50 kg\"*\n\n"
            f"3. **Finished Products & Bill of Materials (BOM)**:\n"
            f"   - *\"Create a product named Margherita Pizza with price 12.99 and BOM components: Paneer 200g\"*\n"
            f"   - *\"List products\"*\n\n"
            f"4. **Machinery & Conditions**:\n"
            f"   - *\"List all factory machines and their parameter boundaries\"*\n\n"
            f"5. **ARIMA Sales Forecasting**:\n"
            f"   - *\"Get 7-day expected sales forecasting using ARIMA analysis\"*\n"
            f"   - *\"Predict material demand\"*\n\n"
            f"6. **Inventory Stats**:\n"
            f"   - *\"Get inventory stats\"*"
        )
