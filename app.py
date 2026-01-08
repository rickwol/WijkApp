import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import folium
from streamlit_folium import st_folium
import os

# Page config
st.set_page_config(page_title="Netherlands Voltage Rooms", layout="wide")

# Title
st.markdown("""
<div style='background-color: #2563eb; padding: 20px; border-radius: 5px; margin-bottom: 20px;'>
    <h1 style='color: white; margin: 0;'>Netherlands Medium Voltage Rooms</h1>
    <p style='color: #bfdbfe; margin: 5px 0 0 0;'>Click on a voltage room marker to view its electricity profile and connected objects</p>
</div>
""", unsafe_allow_html=True)

# Load data
@st.cache_data
def load_data():
    try:
        # Try comma first, then semicolon
        try:
            voltage_rooms = pd.read_csv('VoltageRooms.csv')
        except:
            voltage_rooms = pd.read_csv('VoltageRooms.csv', sep=';')
        
        # Load profiles with semicolon delimiter and European decimal format
        try:
            profiles = pd.read_csv('profiles.csv', sep=';', decimal=',')
        except:
            profiles = pd.read_csv('profiles.csv', decimal=',')
        
        # Convert power_kw to numeric if it's not already
        if 'power_kw' in profiles.columns:
            profiles['power_kw'] = pd.to_numeric(profiles['power_kw'], errors='coerce')
        
        return voltage_rooms, profiles
    except FileNotFoundError as e:
        st.error(f"Error loading CSV files: {e}")
        st.info("""
        Please ensure the following files are in the same directory:
        - **VoltageRooms.csv** with columns: id, name, latitude, longitude
        - **profiles.csv** with columns: voltage_room_id (or room_id), timestamp, power_kw (or power/load)
        """)
        return None, None

def load_room_objects(room_id):
    """Load objects associated with a specific voltage room"""
    try:
        filename = f"{room_id}.csv"
        if os.path.exists(filename):
            try:
                # Try with semicolon delimiter first
                objects_df = pd.read_csv(filename, sep=',')
            except:
                try:
                    objects_df = pd.read_csv(filename)
                except:
                    return None
            
            # Handle the unnamed index column if it exists
            if '' in objects_df.columns or 'Unnamed: 0' in objects_df.columns:
                objects_df = objects_df.drop(columns=[col for col in objects_df.columns if col == '' or col.startswith('Unnamed')])
            
            return objects_df
        return None
    except Exception as e:
        st.warning(f"Could not load objects for room {room_id}: {e}")
        return None

def rd_to_wgs84(x, y):
    """
    Convert RD (Rijksdriehoekscoördinaten) to WGS84 (latitude, longitude)
    Using the official transformation formulas from Kadaster
    """
    # Reference points for RD
    x0 = 155000.0
    y0 = 463000.0
    
    # Coefficients for latitude calculation
    Kp = [0, 2, 0, 2, 0, 2, 1, 4, 2, 4, 1]
    Kq = [1, 0, 2, 1, 3, 2, 0, 0, 3, 1, 1]
    Kpq = [3235.65389, -32.58297, -0.24750, -0.84978, -0.06550, -0.01709,
           -0.00738, 0.00530, -0.00039, 0.00033, -0.00012]
    
    # Coefficients for longitude calculation
    Lp = [1, 1, 1, 3, 1, 3, 0, 3, 1, 0, 2, 5]
    Lq = [0, 1, 2, 0, 3, 1, 1, 2, 4, 2, 0, 0]
    Lpq = [5260.52916, 105.94684, 2.45656, -0.81885, 0.05594, -0.05607,
           0.01199, -0.00256, 0.00128, 0.00022, -0.00022, 0.00026]
    
    # Reference point for WGS84
    phi0 = 52.15517440
    lambda0 = 5.38720621
    
    # Normalize
    dx = (x - x0) * 1e-5
    dy = (y - y0) * 1e-5
    
    # Calculate latitude
    phi = phi0
    for k in range(len(Kpq)):
        phi += Kpq[k] * (dx ** Kp[k]) * (dy ** Kq[k])
    phi = phi / 3600
    
    # Calculate longitude
    lambda_deg = lambda0
    for l in range(len(Lpq)):
        lambda_deg += Lpq[l] * (dx ** Lp[l]) * (dy ** Lq[l])
    lambda_deg = lambda_deg / 3600
    
    return phi, lambda_deg

voltage_rooms, profiles = load_data()

if voltage_rooms is not None and profiles is not None:
    # Normalize column names
    if 'lat' in voltage_rooms.columns:
        voltage_rooms['latitude'] = voltage_rooms['lat']
    if 'lon' in voltage_rooms.columns or 'lng' in voltage_rooms.columns:
        voltage_rooms['longitude'] = voltage_rooms.get('lon', voltage_rooms.get('lng'))
    
    # Profile column normalization
    if 'room_id' in profiles.columns:
        profiles['voltage_room_id'] = profiles['room_id']
    if 'time' in profiles.columns or 'date' in profiles.columns:
        profiles['timestamp'] = profiles.get('time', profiles.get('date'))
    if 'power' in profiles.columns or 'load' in profiles.columns:
        profiles['power_kw'] = profiles.get('power', profiles.get('load'))
    
    # Initialize session state for selected room
    if 'selected_room_id' not in st.session_state:
        st.session_state.selected_room_id = None
    if 'show_objects' not in st.session_state:
        st.session_state.show_objects = False
    
    # Add reset button at the top
    if st.session_state.selected_room_id is not None:
        if st.button("🔄 Reset Map View", type="primary"):
            st.session_state.selected_room_id = None
            st.session_state.show_objects = False
            st.rerun()
    
    # Create two columns
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("Voltage Room Locations")
        
        # Determine map center and zoom based on selection
        if st.session_state.selected_room_id is not None:
            selected_for_map = voltage_rooms[voltage_rooms['id'] == st.session_state.selected_room_id].iloc[0]
            center_lat = selected_for_map['latitude']
            center_lon = selected_for_map['longitude']
            zoom_level = 15
        else:
            center_lat = voltage_rooms['latitude'].mean()
            center_lon = voltage_rooms['longitude'].mean()
            zoom_level = 7
        
        # Create Folium map
        m = folium.Map(location=[center_lat, center_lon], zoom_start=zoom_level)
        
        # Add markers for each voltage room
        for idx, row in voltage_rooms.iterrows():
            room_id = row['id']
            room_name = row.get('name', room_id)
            
            # Check if this room is selected
            is_selected = (st.session_state.selected_room_id == room_id)
            
            # Create marker with appropriate color
            folium.CircleMarker(
                location=[row['latitude'], row['longitude']],
                radius=12 if is_selected else 8,
                popup=folium.Popup(f"<b>{room_name}</b><br>ID: {room_id}", max_width=200),
                tooltip=room_name,
                color='white',
                fillColor='#ef4444' if is_selected else '#3b82f6',
                fillOpacity=0.8,
                weight=2
            ).add_to(m)
        
        # If a room is selected, add its associated objects
        if st.session_state.selected_room_id is not None and st.session_state.show_objects:
            room_objects = load_room_objects(st.session_state.selected_room_id)
            
            if room_objects is not None and len(room_objects) > 0:
                # Add markers for each object
                for idx, obj in room_objects.iterrows():
                    # Get RD coordinates
                    rd_x = obj.get('x_coordinate')
                    rd_y = obj.get('y_coordinate')
                    
                    if pd.notna(rd_x) and pd.notna(rd_y):
                        # Convert RD to WGS84
                        try:
                            obj_lat, obj_lon = rd_to_wgs84(float(rd_x), float(rd_y))
                            
                            # Create popup content
                            popup_html = f"""
                            <div style='min-width: 200px;'>
                                <b>{obj.get('Gebruiksdoel', 'Object')}</b><br>
                                <b>Type:</b> {obj.get('Type', 'N/A')}<br>
                                <b>Adres:</b> {obj.get('Hoofdadres', 'N/A')}<br>
                                <b>ID:</b> {obj.get('ID', 'N/A')}<br>
                                <b>Oppervlakte:</b> {obj.get('Oppervlakte', 'N/A')} m²
                            </div>
                            """
                            
                            folium.CircleMarker(
                                location=[obj_lat, obj_lon],
                                radius=6,
                                popup=folium.Popup(popup_html, max_width=250),
                                tooltip=str(obj.get('Hoofdadres', obj.get('ID', 'Object'))),
                                color='white',
                                fillColor='#10b981',
                                fillOpacity=0.7,
                                weight=1
                            ).add_to(m)
                        except Exception as e:
                            # Skip objects with invalid coordinates
                            st.error("Invalid coordinates")
                            continue
                
                st.info(f"📍 Showing {len(room_objects)} objects connected to this voltage room")
        
        # Display map and capture click events
        map_data = st_folium(m, width=None, height=600, key=f"folium_map_{st.session_state.selected_room_id}_{st.session_state.show_objects}")
        
        # Check if a marker was clicked
        if map_data and map_data.get('last_object_clicked'):
            clicked_lat = map_data['last_object_clicked']['lat']
            clicked_lon = map_data['last_object_clicked']['lng']
            
            # Find the closest voltage room to the clicked location
            voltage_rooms['distance'] = ((voltage_rooms['latitude'] - clicked_lat)**2 + 
                                        (voltage_rooms['longitude'] - clicked_lon)**2)**0.5
            closest_room = voltage_rooms.loc[voltage_rooms['distance'].idxmin()]
            
            # Update selected room if it's different
            if st.session_state.selected_room_id != closest_room['id']:
                st.session_state.selected_room_id = closest_room['id']
                st.session_state.show_objects = True
                st.rerun()
    
    with col2:
        st.subheader("Electricity Profile")
        
        # Get selected room
        selected_room = None
        if st.session_state.selected_room_id is not None:
            selected_room = voltage_rooms[voltage_rooms['id'] == st.session_state.selected_room_id].iloc[0]
        
        if selected_room is not None:
            # Display room info
            st.markdown(f"""
            <div style='background-color: #f3f4f6; padding: 15px; border-radius: 5px; margin-bottom: 20px;'>
                <h3 style='margin: 0 0 10px 0;'>{selected_room.get('name', selected_room['id'])}</h3>
                <p style='margin: 5px 0; color: #666;'>
                    <strong>ID:</strong> {selected_room['id']} | 
                    <strong>Lat:</strong> {selected_room['latitude']:.4f} | 
                    <strong>Lng:</strong> {selected_room['longitude']:.4f}
                </p>
            </div>
            """, unsafe_allow_html=True)
            
            # Show objects info if available
            room_objects = load_room_objects(selected_room['id'])
            if room_objects is not None and len(room_objects) > 0:
                with st.expander(f"📋 Connected Objects ({len(room_objects)})", expanded=False):
                    st.dataframe(room_objects, use_container_width=True, height=200)
            
            # Filter profiles for selected room
            room_profiles = profiles[profiles['voltage_room_id'] == selected_room['id']].copy()
            
            if len(room_profiles) > 0:
                # Convert timestamp to datetime and extract date
                room_profiles['timestamp'] = pd.to_datetime(room_profiles['timestamp'])
                room_profiles['date'] = room_profiles['timestamp'].dt.date
                
                # Group by date and find max power per day
                daily_max = room_profiles.groupby('date')['power_kw'].max()
                
                # Find the day with highest max power
                peak_day = daily_max.idxmax()
                
                # Initialize session state for selected date if not exists
                if 'selected_date' not in st.session_state or st.session_state.get('last_room_id') != selected_room['id']:
                    st.session_state.selected_date = peak_day
                    st.session_state.last_room_id = selected_room['id']
                
                # Get unique dates and create date selector
                unique_dates = sorted(room_profiles['date'].unique())
                
                st.markdown("### Select Date")
                col_date1, col_date2 = st.columns([3, 1])
                
                with col_date1:
                    selected_date = st.selectbox(
                        "Choose a day to view:",
                        unique_dates,
                        index=unique_dates.index(st.session_state.selected_date),
                        format_func=lambda x: f"{x} {'⭐ (Peak Day)' if x == peak_day else ''}",
                        key=f"date_selector_{selected_room['id']}"
                    )
                    st.session_state.selected_date = selected_date
                
                with col_date2:
                    st.metric("Peak Day", f"{daily_max[peak_day]:.1f} kW", 
                             delta=f"{peak_day}")
                
                # Filter data for selected date
                day_profiles = room_profiles[room_profiles['date'] == selected_date]
                
                # Find the absolute highest value across all data for this room
                max_power_overall = room_profiles['power_kw'].max()
                max_power_timestamp = room_profiles.loc[room_profiles['power_kw'].idxmax(), 'timestamp']
                
                # Create line chart for selected day
                fig_profile = go.Figure()
                fig_profile.add_trace(go.Scatter(
                    x=day_profiles['timestamp'],
                    y=day_profiles['power_kw'],
                    mode='lines',
                    name='Power (kW)',
                    line=dict(color='#ef4444' if selected_date == peak_day else '#3b82f6', width=2)
                ))
                
                # Add vertical line for highest value throughout the entire year
                fig_profile.add_hline(
                    y=max_power_overall,
                    line_dash="dash",
                    line_color="red",
                    line_width=2,
                    annotation_text=f"Year Peak: {max_power_overall:.1f} kW",
                    annotation_position="top"
                )
                
                # Highlight max point of the day
                max_idx = day_profiles['power_kw'].idxmax()
                max_point = day_profiles.loc[max_idx]
                
                fig_profile.add_trace(go.Scatter(
                    x=[max_point['timestamp']],
                    y=[max_point['power_kw']],
                    mode='markers',
                    name='Day Peak',
                    marker=dict(color='#ef4444', size=12, symbol='star'),
                    showlegend=True
                ))
                
                fig_profile.update_layout(
                    title=f"Power Profile for {selected_date}",
                    xaxis_title="Time",
                    yaxis_title="Power (kW)",
                    height=400,
                    hovermode='x unified',
                    margin=dict(l=0, r=0, t=40, b=0)
                )
                
                st.plotly_chart(fig_profile, use_container_width=True)
                
                # Show info about the year peak if it's on a different day
                if selected_date != max_power_timestamp.date():
                    st.info(f"ℹ️ The highest power value for this room ({max_power_overall:.1f} kW) occurred on {max_power_timestamp.date()} at {max_power_timestamp.strftime('%H:%M')}")
                
                # Statistics for selected day
                st.markdown("### Daily Statistics")
                stat_col1, stat_col2, stat_col3 = st.columns(3)
                
                with stat_col1:
                    st.metric("Data Points", len(day_profiles))
                
                with stat_col2:
                    st.metric("Max Power", f"{day_profiles['power_kw'].max():.1f} kW")
                
                with stat_col3:
                    st.metric("Avg Power", f"{day_profiles['power_kw'].mean():.1f} kW")
            else:
                st.warning("⚠️ No profile data found for this voltage room.")
        else:
            st.info("👈 Click on a voltage room marker on the map to view its electricity profile and connected objects")
else:
    st.error("Unable to load data. Please check that the CSV files are present and properly formatted.")