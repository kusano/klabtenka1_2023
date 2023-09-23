import os
import sys
import random
import time
import requests
from typing import List

# ゲームサーバのアドレス / トークン
GAME_SERVER = os.getenv('GAME_SERVER', 'https://gbc2023.tenka1.klab.jp')
TOKEN = os.getenv('TOKEN', 'YOUR_TOKEN')

N = 5
Dj = [+1, 0, -1, 0]
Dk = [0, +1, 0, -1]
TOTAL_TURN = 294

session = requests.Session()


# ゲームサーバのAPIを叩く
def call_api(x: str) -> dict:
    url = f'{GAME_SERVER}{x}'
    # 5xxエラーまたはRequestExceptionの際は100ms空けて5回までリトライする
    for _ in range(5):
        print(url, flush=True)
        try:
            response = session.get(url)

            if response.status_code == 200:
                return response.json()

            if 500 <= response.status_code < 600:
                print(response.status_code)
                time.sleep(0.1)
                continue

            raise Exception('Api Error status_code:{}'.format(response.status_code))

        except requests.RequestException as e:
            print(e)
            time.sleep(0.1)
    raise Exception('Api Error')


# 指定したmode, delayで練習試合開始APIを呼ぶ
def call_start(mode: int, delay: int):
    return call_api(f"/api/start/{TOKEN}/{mode}/{delay}")


# dir方向に移動するように移動APIを呼ぶ
def call_move(game_id: int, dir0: str, dir5: str):
    return call_api(f"/api/move/{TOKEN}/{game_id}/{dir0}/{dir5}")


# game_idを取得する
# 環境変数で指定されていない場合は練習試合のgame_idを返す
def get_game_id() -> int:
    # 環境変数にGAME_IDが設定されている場合これを優先する
    if os.getenv('GAME_ID'):
        return int(os.getenv('GAME_ID'))

    # start APIを呼び出し練習試合のgame_idを取得する
    start = call_start(0, 0)
    if start['status'] == 'ok' or start['status'] == 'started':
        return start['game_id']

    raise Exception(f'Start Api Error : {start}')


class Agent:
    def __init__(self, i: int, j: int, k: int, d: int):
        self.i = i
        self.j = j
        self.k = k
        self.d = d


class Cell:
    def __init__(self, owner: int, val: int):
        self.owner = owner
        self.val = val


class GameLogic:
    def __init__(self, move: dict):
        self.field: List[Cell] = []
        self.agents: List[Agent] = []
        self.turn: int = move['turn']
        self.move: List[int] = list(move['move'])
        self.score: List[int] = list(move['score'])
        self.area: List[int] = [0, 0, 0]
        self.special: List[int] = list(move['special'])
        for i in range(6):
            for j in range(N):
                for k in range(N):
                    owner = move['field'][i][j][k][0]
                    self.field.append(Cell(owner, move['field'][i][j][k][1]))
                    if owner >= 0:
                        self.area[owner] += 1

        for agent in move['agent']:
            self.agents.append(Agent(agent[0], agent[1], agent[2], agent[3]))

    def get_cell(self, i: int, j: int, k: int) -> Cell:
        return self.field[self.field_idx(i, j, k)]

    # move_list に従ってゲームを進行する
    def progress(self, member_id: int, move_list: List[int]):
        assert len(move_list) % 6 == 0
        counter = bytearray(6 * N * N)
        fis = [0] * 6
        for i in range(0, len(move_list), 6):
            # エージェントの移動処理
            for idx in range(6):
                self.move[idx] = move_list[i + self.func1(member_id, idx)]
                if self.move[idx] == -1 or self.move[idx] >= 4:
                    continue
                self.rotate_agent(idx, self.move[idx])
                self.move_forward(idx)
                ii = self.agents[idx].i
                jj = self.agents[idx].j
                kk = self.agents[idx].k
                fis[idx] = self.field_idx(ii, jj, kk)
                counter[fis[idx]] |= 1 << idx

            # フィールドの更新処理 (通常移動)
            for idx in range(6):
                if self.move[idx] == -1 or self.move[idx] >= 4:
                    continue
                owner_id = idx if idx < 3 else 5 - idx
                if self.check_counter(counter[fis[idx]], owner_id, idx) or self.field[fis[idx]].owner == owner_id:
                    self.paint(owner_id, fis[idx])

            for idx in range(6):
                if self.move[idx] == -1 or self.move[idx] >= 4:
                    continue
                counter[fis[idx]] = 0

            # フィールドの更新処理 (特殊移動)
            special_fis: set[int] = set()
            for idx in range(6):
                if self.move[idx] <= 3:
                    continue
                self.special[idx] -= 1
                owner_id = idx if idx < 3 else 5 - idx
                if self.move[idx] <= 7:
                    # 5 マス前進
                    self.rotate_agent(idx, self.move[idx])
                    for p in range(5):
                        self.move_forward(idx)
                        ii = self.agents[idx].i
                        jj = self.agents[idx].j
                        kk = self.agents[idx].k
                        fi = self.field_idx(ii, jj, kk)
                        special_fis.add(fi)
                        counter[fi] |= 1 << owner_id
                else:
                    # 指定したマスに移動
                    m = self.move[idx] - 8
                    mi = self.func1(owner_id, m // 25)
                    mj = m // 5 % 5
                    mk = m % 5
                    fi = self.field_idx(mi, mj, mk)
                    special_fis.add(fi)
                    counter[fi] |= 1 << owner_id
                    for d in range(4):
                        self.agents[idx].i = mi
                        self.agents[idx].j = mj
                        self.agents[idx].k = mk
                        self.agents[idx].d = d
                        self.move_forward(idx)
                        ii = self.agents[idx].i
                        jj = self.agents[idx].j
                        kk = self.agents[idx].k
                        fi = self.field_idx(ii, jj, kk)
                        special_fis.add(fi)
                        counter[fi] |= 1 << owner_id
                    self.agents[idx].i = mi
                    self.agents[idx].j = mj
                    self.agents[idx].k = mk
                    self.agents[idx].d = 0

            for fi in special_fis:
                if counter[fi] == 1:
                    self.force_paint(0, fi)
                elif counter[fi] == 2:
                    self.force_paint(1, fi)
                elif counter[fi] == 4:
                    self.force_paint(2, fi)
                counter[fi] = 0

            # score 更新
            if self.turn >= TOTAL_TURN // 2:
                self.add_score()

            self.turn += 1

    # ownerId のみが塗ろうとしているかを判定
    @staticmethod
    def check_counter(counter: int, owner_id: int, idx: int) -> bool:
        return (counter == 1 << idx) or (counter == ((1 << idx) | (1 << owner_id)))

    # score 更新
    def add_score(self):
        for i in range(3):
            self.score[i] += self.area[i]

    # move 用
    @staticmethod
    def func1(member_id: int, pos: int) -> int:
        i0 = member_id // 3
        i1 = member_id % 3
        j0 = pos // 3
        j1 = pos % 3
        return ((j0 + 1) * i1 + j1) % 3 + (i0 + j0) % 2 * 3

    # field_idx が fi のマスを owner_id が塗る (通常移動)
    def paint(self, owner_id: int, fi: int):
        if self.field[fi].owner == -1:
            # 誰にも塗られていない場合は owner_id で塗る
            self.area[owner_id] += 1
            self.field[fi].owner = owner_id
            self.field[fi].val = 2
        elif self.field[fi].owner == owner_id:
            # owner_id で塗られている場合は完全に塗られた状態に上書きする
            self.field[fi].val = 2
        elif self.field[fi].val == 1:
            # owner_id 以外で半分塗られた状態の場合は誰にも塗られていない状態にする
            self.area[self.field[fi].owner] -= 1
            self.field[fi].owner = -1
            self.field[fi].val = 0
        else:
            # owner_id 以外で完全に塗られた状態の場合は半分塗られた状態にする
            self.field[fi].val -= 1

    # field_idx が fi のマスを owner_id が塗る (特殊移動)
    def force_paint(self, owner_id: int, fi: int):
        if self.field[fi].owner != owner_id:
            self.area[owner_id] += 1
            if self.field[fi].owner != -1:
                self.area[self.field[fi].owner] -= 1
        self.field[fi].owner = owner_id
        self.field[fi].val = 2

    # idx のエージェントを v 方向に回転させる
    def rotate_agent(self, idx: int, v: int):
        self.agents[idx].d += v
        self.agents[idx].d %= 4

    # idx のエージェントを前進させる
    def move_forward(self, idx: int):
        i = self.agents[idx].i
        j = self.agents[idx].j
        k = self.agents[idx].k
        d = self.agents[idx].d
        jj = j + Dj[d]
        kk = k + Dk[d]
        if jj >= N:
            self.agents[idx].i = i // 3 * 3 + (i % 3 + 1) % 3  # [1, 2, 0, 4, 5, 3][i]
            self.agents[idx].j = k
            self.agents[idx].k = N - 1
            self.agents[idx].d = 3
        elif jj < 0:
            self.agents[idx].i = (1 - i // 3) * 3 + (4 - i % 3) % 3  # [4, 3, 5, 1, 0, 2][i]
            self.agents[idx].j = 0
            self.agents[idx].k = N - 1 - k
            self.agents[idx].d = 0
        elif kk >= N:
            self.agents[idx].i = i // 3 * 3 + (i % 3 + 2) % 3  # [2, 0, 1, 5, 3, 4][i]
            self.agents[idx].j = N - 1
            self.agents[idx].k = j
            self.agents[idx].d = 2
        elif kk < 0:
            self.agents[idx].i = (1 - i // 3) * 3 + (3 - i % 3) % 3  # [3, 5, 4, 0, 2, 1][i]
            self.agents[idx].j = N - 1 - j
            self.agents[idx].k = 0
            self.agents[idx].d = 1
        else:
            self.agents[idx].j = jj
            self.agents[idx].k = kk

    # (i, j, k) を field の添え字にする
    @staticmethod
    def field_idx(i: int, j: int, k: int) -> int:
        return (i * N + j) * N + k


class Program:
    @staticmethod
    def use_random_special(next_dir: str) -> str:
        # 50%で直進の必殺技を使用
        if random.random() <= 0.5:
            return next_dir + "s"
        # 50%でランダムな場所に瞬間移動
        i = random.randint(0, 5)
        j = random.randint(0, 4)
        k = random.randint(0, 4)
        return f"{i}-{j}-{k}"

    def solve(self):
        game_id = get_game_id()
        next_dir0 = str(random.randint(0, 3))
        next_dir5 = str(random.randint(0, 3))
        while True:
            # 移動APIを呼ぶ
            move = call_move(game_id, next_dir0, next_dir5)
            print(f"status = {move['status']}", file=sys.stderr, flush=True)
            if move['status'] == "already_moved":
                continue
            elif move['status'] != 'ok':
                break
            print(f"turn = {move['turn']}", file=sys.stderr, flush=True)
            print(f"score = {move['score'][0]} {move['score'][1]} {move['score'][2]}", file=sys.stderr, flush=True)
            
            # 4方向で移動した場合を全部シミュレーションする
            best_c = -10**10
            best_d = []
            for d0 in range(4):
                for d5 in range(4):
                    m = GameLogic(move)
                    m.progress(0, [d0, -1, -1, -1, -1, d5])
                    # 自身のエージェントで塗られているマス数をカウントする
                    c0 = 0
                    for i in range(6):
                        for j in range(N):
                            for k in range(N):
                                cell = m.get_cell(i, j, k)
                                if cell.owner==0:
                                    c0 += 100 + cell.val
                                elif cell.owner!=-1:
                                    c0 -= 50 + cell.val
                    for d0_2 in range(4):
                        for d5_2 in range(4):
                            for d0_3 in range(4):
                                m = GameLogic(move)
                                m.progress(0, [d0, -1, -1, -1, -1, d5])
                                m.progress(0, [d0_2, -1, -1, -1, -1, d5_2])
                                m.progress(0, [d0_3, -1, -1, -1, -1, -1])
                                # 自身のエージェントで塗られているマス数をカウントする
                                c1 = 0
                                for i in range(6):
                                    for j in range(N):
                                        for k in range(N):
                                            cell = m.get_cell(i, j, k)
                                            if cell.owner==0:
                                                c1 += 100 + cell.val
                                            elif cell.owner!=-1:
                                                c1 -= 50 + cell.val
                                c = c0+c1*10
                                # 最も多くのマスを自身のエージェントで塗れる移動方向のリストを保持する
                                if c > best_c:
                                    best_c = c
                                    best_d = [(d0, d5)]
                                elif c == best_c:
                                    best_d.append((d0, d5))

            if random.random()<0.1:
                # たまには完全ランダムに移動
                print("random!!!")
                best0 = random.randint(0, 3)
                best5 = random.randint(0, 3)
            else:                
                # 最も多くのマスを自身のエージェントで塗れる移動方向のリストからランダムで方向を決める
                best0, best5 = random.choice(best_d)
                next_dir0 = str(best0)
                next_dir5 = str(best5)

            """
            # 必殺技の使用回数が残っている場合はランダムな確率で使用する
            if move['special'][0] != 0 and random.random() <= 0.1:
                next_dir0 = self.use_random_special(next_dir0)
            if move['special'][5] != 0 and random.random() <= 0.1:
                next_dir5 = self.use_random_special(next_dir5)
            """


if __name__ == "__main__":
    Program().solve()
