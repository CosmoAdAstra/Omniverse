"""

--- 작성일 :2024.04.30 송인용 ---
EKF 분석 작업할때 주피터 노트북으로 키면서 분석하는 것보다 언제든지 웹 접속해서 하는게 더 편할 것 같아서 웹서버를 만들었다.
근데 당일날 작업 하다보니 배보다 배꼽이 커지길래 분석은 그냥 주피터 노트북으로 하도록 생각을 바꿨다.

다만 현재 MobileX 시간이 동일한 NTP 로 동기화 되고 있길래 비교적 간단한한데 반복이라 귀찮은 작업들

로봇 전진, 후진 할때 시간 측정 등 간단해서 오류 발생 가능성이 적은 코드들은 여전히 웹서버로 미리 만들어 놓고 상시 켜두면 
처음 의도대로 귀찮음을 줄일 수 있을 거 같아서 최소한으로 필요한 기능들 위주로 구현은 하기로 했다.



"""



from flask import Flask, render_template, jsonify, request, redirect, url_for
from db_stat import DBStatManager  ,DBSystemManager
from datetime import datetime
import math
import json
import matplotlib.pyplot as plt

app = Flask(__name__)
db_stat_manager = DBStatManager('/home/netai/dt_server/UWB_EKF/config.json')  

#!!!! 웹서버에서 전역변수 같은 진빠는 나중에 꼭 변경하도록
global_movements = []

@app.route('/', methods=['GET', 'POST'])
def index():

    # 처음 렌더링 할때 수행되는 작업
    now = datetime.utcnow()
    end_default = now.strftime('%Y-%m-%d %H:%M:%S')  # UTC 기준 현재 시간을 문자열로
    start_default = "2024-04-30 01:00:00"  # 기본 시작 시간을 설정

    db_manager = DBSystemManager('/home/netai/dt_server/UWB_EKF/config.json')
    tag_list = db_manager.get_taglist()  # 태그 목록 가져오기

    if request.method == 'POST':
        search_term = request.form.get('search_term', '')
        filtered_tags = [tag for tag in tag_list if search_term in tag[1]]  # kube_id를 포함하는 태그만 필터링
    else:
        filtered_tags = tag_list

    return render_template('index.html', start_default=start_default, end_default=end_default, tags=filtered_tags)


@app.route('/analyze', methods=['POST'])
def analyze():

    kwargs = {'tag_id': request.form['tag_id']}
    if request.form['start']:
        kwargs['start'] = request.form['start']
    if request.form['end']:
        kwargs['end'] = request.form['end']

    
    # Redirect to the analysis page with the parameters
    return redirect(url_for('show_analysis', **kwargs))

@app.route('/analysis/<tag_id>/<start>/<end>')
def show_analysis(tag_id, start, end):
    # Perform the analysis using the provided parameters
    # Fetch movements data and pass it to the analysis page

    movements = db_stat_manager.get_tag_movements(tag_id, start, end)
    row_count, time_seconds = made_footer(movements)

    # The analysis page will use D3.js to visualize this data
    return render_template('analysis_d3.html', movements=movements, row_count=row_count, time_seconds=time_seconds)

@app.route('/data/<tag_id>')
def get_data(tag_id):
    # Fetch data for the specified tag_id
    movements = db_stat_manager.get_tag_movements(tag_id, '2024-01-01', '2024-01-31')
    return jsonify(movements)

@app.route('/distance_error')
def distance_error():
    tag_id = request.args.get('tag_id', '')
    start = request.args.get('start', '')
    end = request.args.get('end', '')

    movements = db_stat_manager.get_tag_movements(tag_id, start, end)
    """
    movements_json = json.dumps([{
        'x': m[0],
        'y': m[1],
        'timestamp': m[2].isoformat() if hasattr(m[2], 'isoformat') else str(m[2])
    } for m in movements])
    print("Movements JSON:", movements_json)  """
    global global_movements
    row_count, time_seconds = made_footer(movements)
    global_movements = movements
    return render_template('distance.html', tag_id=tag_id, start=start, end=end, row_count=row_count, time_seconds=time_seconds)

def calculate_speed(x1, y1, x2, y2, time_seconds):
    distance = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
    return distance / time_seconds

def made_footer(movements) :
    row_count = len(movements)

        # 시간 차이 계산
    if movements:
        times = [movement[2] for movement in movements]
        min_time = min(times)
        max_time = max(times)
        time_seconds = (max_time - min_time).total_seconds()
    else:
        time_seconds = 0  # 데이터가 없을 경우 0초로 설정

    return row_count, time_seconds

def calculate_theoretical_position(start_x, start_y, end_x, end_y, total_seconds, elapsed_time):
    """ Calculate the theoretical position at a given elapsed time. """
    dx = end_x - start_x
    dy = end_y - start_y
    distance = math.sqrt(dx**2 + dy**2)
    speed = distance / total_seconds # m/s
    proportion = elapsed_time / total_seconds
    theoretical_x = start_x + dx * proportion
    theoretical_y = start_y + dy * proportion
    return theoretical_x, theoretical_y

def calculate_errors(movements, start_x, start_y, end_x, end_y, total_seconds):
    """ Calculate errors between theoretical and actual positions over time. """
    errors = []
    for x, y, timestamp in movements:
        elapsed_time = (timestamp - movements[0][2]).total_seconds()
        tx, ty = calculate_theoretical_position(start_x, start_y, end_x, end_y, total_seconds, elapsed_time)
        error = math.sqrt((tx - x)**2 + (ty - y)**2) * 100  # Convert to cm
        errors.append((timestamp, error))
    return errors

def plot_errors(errors):
    """ Plot the errors over time. """
    times = [error[0] for error in errors]
    values = [error[1] for error in errors]
    plt.figure(figsize=(10, 5))
    plt.plot(times, values, marker='o', linestyle='-', color='r')
    plt.title('Distance Errors Over Time')
    plt.xlabel('Time')
    plt.ylabel('Error (cm)')
    plt.grid(True)
    plt.close()

@app.route('/calculate_error', methods=['POST'])
def calculate_error():
    data = request.get_json()
    calculation_type = data.get('calculationType')
    start_x = float(data.get('start_x', 0))
    start_y = float(data.get('start_y', 0))
    end_x = float(data.get('end_x', 0))
    end_y = float(data.get('end_y', 0))
    time_seconds = float(data.get('second', 0))
    speed = float(data.get('speed', 0))
    global global_movements # 전역변수 두명이상만 사용해도 난리나니까 만약 이후에 계속 해당 코드를 사용하게 되면 최우선으로 변경

    try:
        if calculation_type == 'speed':
            speed = calculate_speed(start_x, start_y, end_x, end_y, time_seconds)
            return jsonify({'message': f"Calculated Speed: {speed:.2f} m/s", 'status': 'success', 'speed': speed})
        elif calculation_type == 'position':
            message = "Position calculation not implemented yet"
            print(message)
        elif calculation_type == 'error':
            errors = calculate_errors(global_movements, start_x, start_y, end_x, end_y, time_seconds)


            average_error = sum(error[1] for error in errors) / len(errors)

                        # 에러 그래프 생성

            print(f"Average UWB error: {average_error:.2f} cm") 
        return jsonify({'message': f"Average UWB error: {average_error:.2f} cm", 'status': 'error'})
    except Exception as e:
        return jsonify



if __name__ == '__main__':
    app.run(debug=True)
