"""
prg_parser.py
Przepisanie BimmerDis.cpp na Python.
Dekoduje pliki BMW EDIABAS .prg (BEST/1) i zwraca strukturę danych
zawierającą metadane, joby, tabele i komentarze.

Oryginał: BimmerDis (C++) by radelbro
Licencja oryginału: oparty na ediabaslib (GPL-3.0)
"""

import struct
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Stałe

XOR_KEY = 0xF7
HEADER_SIZE = 0x9C


# ---------------------------------------------------------------------------
# Tabela rejestrów (OpArg)

OA_MAP = {
    0x00: "B0", 0x01: "B1", 0x02: "B2", 0x03: "B3",
    0x04: "B4", 0x05: "B5", 0x06: "B6", 0x07: "B7",
    0x08: "B8", 0x09: "B9", 0x0A: "BA", 0x0B: "BB",
    0x0C: "BC", 0x0D: "BD", 0x0E: "BE", 0x0F: "BF",
    0x10: "I0", 0x11: "I1", 0x12: "I2", 0x13: "I3",
    0x14: "I4", 0x15: "I5", 0x16: "I6", 0x17: "I7",
    0x18: "L0", 0x19: "L1", 0x1A: "L2", 0x1B: "L3",
    0x1C: "S0", 0x1D: "S1", 0x1E: "S2", 0x1F: "S3",
    0x20: "S4", 0x21: "S5", 0x22: "S6", 0x23: "S7",
    0x24: "F0", 0x25: "F1", 0x26: "F2", 0x27: "F3",
    0x28: "F4", 0x29: "F5", 0x2A: "F6", 0x2B: "F7",
    0x2C: "S8", 0x2D: "S9", 0x2E: "SA", 0x2F: "SB",
    0x30: "SC", 0x31: "SD", 0x32: "SE", 0x33: "SF",
    0x80: "A0", 0x81: "A1", 0x82: "A2", 0x83: "A3",
    0x84: "A4", 0x85: "A5", 0x86: "A6", 0x87: "A7",
    0x88: "A8", 0x89: "A9", 0x8A: "AA", 0x8B: "AB",
    0x8C: "AC", 0x8D: "AD", 0x8E: "AE", 0x8F: "AF",
    0x90: "I8", 0x91: "I9", 0x92: "IA", 0x93: "IB",
    0x94: "IC", 0x95: "ID", 0x96: "IE", 0x97: "IF",
    0x98: "L4", 0x99: "L5", 0x9A: "L6", 0x9B: "L7",
}

# Tabela opcodów: kod -> (mnemonic, arg0_is_near_address)
OC_MAP = {
    0x00: ("move",     False),
    0x01: ("clear",    False),
    0x02: ("comp",     False),
    0x03: ("subb",     False),
    0x04: ("adds",     False),
    0x05: ("mult",     False),
    0x06: ("divs",     False),
    0x07: ("and",      False),
    0x08: ("or",       False),
    0x09: ("xor",      False),
    0x0A: ("not",      False),
    0x0B: ("jump",     True),
    0x0C: ("jtsr",     True),
    0x0D: ("ret",      False),
    0x0E: ("jc",       True),
    0x0F: ("jae",      True),
    0x10: ("jz",       True),
    0x11: ("jnz",      True),
    0x12: ("jv",       True),
    0x13: ("jnv",      True),
    0x14: ("jmi",      True),
    0x15: ("jpl",      True),
    0x16: ("clrc",     False),
    0x17: ("setc",     False),
    0x18: ("asr",      False),
    0x19: ("lsl",      False),
    0x1A: ("lsr",      False),
    0x1B: ("asl",      False),
    0x1C: ("nop",      False),
    0x1D: ("eoj",      False),
    0x1E: ("push",     False),
    0x1F: ("pop",      False),
    0x20: ("scmp",     False),
    0x21: ("scat",     False),
    0x22: ("scut",     False),
    0x23: ("slen",     False),
    0x24: ("spaste",   False),
    0x25: ("serase",   False),
    0x26: ("xconnect", False),
    0x27: ("xhangup",  False),
    0x28: ("xsetpar",  False),
    0x29: ("xawlen",   False),
    0x2A: ("xsend",    False),
    0x2B: ("xsendf",   False),
    0x2C: ("xrequf",   False),
    0x2D: ("xstopf",   False),
    0x2E: ("xkeyb",    False),
    0x2F: ("xstate",   False),
    0x30: ("xboot",    False),
    0x31: ("xreset",   False),
    0x32: ("xtype",    False),
    0x33: ("xvers",    False),
    0x34: ("ergb",     False),
    0x35: ("ergw",     False),
    0x36: ("ergd",     False),
    0x37: ("ergi",     False),
    0x38: ("ergr",     False),
    0x39: ("ergs",     False),
    0x3A: ("a2flt",    False),
    0x3B: ("fadd",     False),
    0x3C: ("fsub",     False),
    0x3D: ("fmul",     False),
    0x3E: ("fdiv",     False),
    0x3F: ("ergy",     False),
    0x40: ("enewset",  False),
    0x41: ("etag",     True),
    0x42: ("xreps",    False),
    0x43: ("gettmr",   False),
    0x44: ("settmr",   False),
    0x45: ("sett",     False),
    0x46: ("clrt",     False),
    0x47: ("jt",       True),
    0x48: ("jnt",      True),
    0x49: ("addc",     False),
    0x4A: ("subc",     False),
    0x4B: ("break",    False),
    0x4C: ("clrv",     False),
    0x4D: ("eerr",     False),
    0x4E: ("popf",     False),
    0x4F: ("pushf",    False),
    0x50: ("atsp",     False),
    0x51: ("swap",     False),
    0x52: ("setspc",   False),
    0x53: ("srevrs",   False),
    0x54: ("stoken",   False),
    0x55: ("parb",     False),
    0x56: ("parw",     False),
    0x57: ("parl",     False),
    0x58: ("pars",     False),
    0x59: ("fclose",   False),
    0x5A: ("jg",       True),
    0x5B: ("jge",      True),
    0x5C: ("jl",       True),
    0x5D: ("jle",      True),
    0x5E: ("ja",       True),
    0x5F: ("jbe",      True),
    0x60: ("fopen",    False),
    0x61: ("fread",    False),
    0x62: ("freadln",  False),
    0x63: ("fseek",    False),
    0x64: ("fseekln",  False),
    0x65: ("ftell",    False),
    0x66: ("ftellln",  False),
    0x67: ("a2fix",    False),
    0x68: ("fix2flt",  False),
    0x69: ("parr",     False),
    0x6A: ("test",     False),
    0x6B: ("wait",     False),
    0x6C: ("date",     False),
    0x6D: ("time",     False),
    0x6E: ("xbatt",    False),
    0x6F: ("tosp",     False),
    0x70: ("xdownl",   False),
    0x71: ("xgetport", False),
    0x72: ("xignit",   False),
    0x73: ("xloopt",   False),
    0x74: ("xprog",    False),
    0x75: ("xraw",     False),
    0x76: ("xsetport", False),
    0x77: ("xsireset", False),
    0x78: ("xstoptr",  False),
    0x79: ("fix2hex",  False),
    0x7A: ("fix2dez",  False),
    0x7B: ("tabset",   False),
    0x7C: ("tabseek",  False),
    0x7D: ("tabget",   False),
    0x7E: ("strcat",   False),
    0x7F: ("pary",     False),
    0x80: ("parn",     False),
    0x81: ("ergc",     False),
    0x82: ("ergl",     False),
    0x83: ("tabline",  False),
    0x84: ("xsendr",   False),
    0x85: ("xrecv",    False),
    0x86: ("xinfo",    False),
    0x87: ("flt2a",    False),
    0x88: ("setflt",   False),
    0x89: ("cfgig",    False),
    0x8A: ("cfgsg",    False),
    0x8B: ("cfgis",    False),
    0x8C: ("a2y",      False),
    0x8D: ("xparraw",  False),
    0x8E: ("hex2y",    False),
    0x8F: ("strcmp",   False),
    0x90: ("strlen",   False),
    0x91: ("y2bcd",    False),
    0x92: ("y2hex",    False),
    0x93: ("shmset",   False),
    0x94: ("shmget",   False),
    0x95: ("ergsysi",  False),
    0x96: ("flt2fix",  False),
    0x97: ("iupdate",  False),
    0x98: ("irange",   False),
    0x99: ("iincpos",  False),
    0x9A: ("tabseeku", False),
    0x9B: ("flt2y4",   False),
    0x9C: ("flt2y8",   False),
    0x9D: ("y42flt",   False),
    0x9E: ("y82flt",   False),
    0x9F: ("plink",    False),
    0xA0: ("pcall",    False),
    0xA1: ("fcomp",    False),
    0xA2: ("plinkv",   False),
    0xA3: ("ppush",    False),
    0xA4: ("ppop",     False),
    0xA5: ("ppushflt", False),
    0xA6: ("ppopflt",  False),
    0xA7: ("ppushy",   False),
    0xA8: ("ppopy",    False),
    0xA9: ("pjtsr",    False),
    0xAA: ("tabsetex", False),
    0xAB: ("ufix2dez", False),
    0xAC: ("generr",   False),
    0xAD: ("ticks",    False),
    0xAE: ("waitex",   False),
    0xAF: ("xopen",    False),
    0xB0: ("xclose",   False),
    0xB1: ("xcloseex", False),
    0xB2: ("xswitch",  False),
    0xB3: ("xsendex",  False),
    0xB4: ("xrecvex",  False),
    0xB5: ("ssize",    False),
    0xB6: ("tabcols",  False),
    0xB7: ("tabrows",  False),
}

# Tryby adresowania
ADDR_MODES = {
    0:  "None",
    1:  "RegS",
    2:  "RegAB",
    3:  "RegI",
    4:  "RegL",
    5:  "Imm8",
    6:  "Imm16",
    7:  "Imm32",
    8:  "ImmStr",
    9:  "IdxImm",
    10: "IdxReg",
    11: "IdxRegImm",
    12: "IdxImmLenImm",
    13: "IdxImmLenReg",
    14: "IdxRegLenImm",
    15: "IdxRegLenReg",
}


# ---------------------------------------------------------------------------
# Struktury danych wynikowych

@dataclass
class PrgInfo:
    bip_version: str = ""
    revision: str = ""
    last_changed: str = ""
    author: str = ""
    package_version: str = ""


@dataclass
class TableRow:
    values: list[str] = field(default_factory=list)


@dataclass
class Table:
    name: str = ""
    columns: list[str] = field(default_factory=list)
    rows: list[TableRow] = field(default_factory=list)


@dataclass
class Job:
    name: str = ""
    address: int = 0
    comments: list[str] = field(default_factory=list)
    disassembly: list[str] = field(default_factory=list)


@dataclass
class PrgFile:
    info: PrgInfo = field(default_factory=PrgInfo)
    uses: list[str] = field(default_factory=list)
    ssize: int = 0
    tables: list[Table] = field(default_factory=list)
    jobs: list[Job] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Klasa parsera

class PrgParser:

    def __init__(self, filepath: str):
        self.path = Path(filepath)
        with open(self.path, "rb") as f:
            self._raw = f.read()
        # Nagłówek czytamy BEZ XOR (tak jak w C++ — readInt32 bez XOR)
        self._header = self._raw[:HEADER_SIZE]

    # --- Niskopoziomowe helpers ---

    def _decrypt_bytes(self, data: bytes) -> bytes:
        """XOR każdego bajtu z 0xF7."""
        return bytes(b ^ XOR_KEY for b in data)

    def _read_decrypted(self, offset: int, count: int) -> bytes:
        """Czyta 'count' bajtów z offsetu i deszyfruje."""
        chunk = self._raw[offset: offset + count]
        if len(chunk) != count:
            raise ValueError(f"Nie można odczytać {count} bajtów z offsetu 0x{offset:X}")
        return self._decrypt_bytes(chunk)

    def _read_int32_raw(self, offset: int) -> int:
        """Czyta int32 little-endian BEZ XOR (jak readInt32 w C++)."""
        return struct.unpack_from("<i", self._raw, offset)[0]

    def _read_int32_dec(self, offset: int) -> int:
        """Czyta int32 little-endian Z XOR."""
        chunk = self._read_decrypted(offset, 4)
        return struct.unpack("<i", chunk)[0]

    def _get_int32_header(self, offset: int) -> int:
        """Czyta int32 z bufora nagłówka BEZ XOR."""
        return struct.unpack_from("<i", self._header, offset)[0]

    def _read_null_string(self, data: bytes) -> str:
        """Zwraca string do pierwszego null-bajtu."""
        end = data.find(b'\x00')
        if end == -1:
            end = len(data)
        return data[:end].decode("latin-1", errors="replace")

    # --- Sekcje parsera ---

    def _parse_info(self) -> PrgInfo:
        """Odpowiednik dumpInfo — czyta metadane z nagłówka pliku."""
        info_offset = self._get_int32_header(0x94)
        data = self._read_decrypted(info_offset, 0x6C)

        bip = f"{data[2]:02X}.{data[1]:02X}.{data[0]:02X}"
        rev1 = struct.unpack_from("<h", data, 0x06)[0]
        rev2 = struct.unpack_from("<h", data, 0x04)[0]
        revision = f"{rev1}.{rev2}"
        last_changed = self._read_null_string(data[0x48: 0x48 + 0x24])
        author = self._read_null_string(data[0x08: 0x08 + 0x40])
        pkg = struct.unpack_from("<I", data, 0x68)[0]
        package_version = f"{pkg:08X}"

        return PrgInfo(
            bip_version=bip,
            revision=revision,
            last_changed=last_changed,
            author=author,
            package_version=package_version,
        )

    def _parse_description(self) -> dict[str, list[str]]:
        """Odpowiednik dumpDescription — czyta komentarze przypisane do jobów."""
        start_offset = self._get_int32_header(0x90)
        if start_offset == -1:
            return {}

        # Liczba bajtów bloku (int32 BEZ XOR)
        num_bytes = self._read_int32_raw(start_offset)
        offset = start_offset + 4

        comments: dict[str, list[str]] = {}
        current_job = ""
        comment_list: list[str] = []
        record: bytearray = bytearray()

        for _ in range(num_bytes):
            b = self._read_decrypted(offset, 1)[0]
            offset += 1
            record.append(b)
            if len(record) >= 1098:
                record.append(10)
            if record[-1] == 10:
                line = record[:-1].decode("latin-1", errors="replace")
                if line.startswith("JOBNAME:"):
                    comments[current_job] = comment_list
                    comment_list = []
                    current_job = line[8:]
                comment_list.append(line)
                record = bytearray()

        comments[current_job] = comment_list
        return comments

    def _parse_uses(self) -> list[str]:
        """Odpowiednik dumpUses — czyta listę plików używanych przez ten plik."""
        uses_offset = self._get_int32_header(0x7C)
        count = self._read_int32_raw(uses_offset)
        offset = uses_offset + 4
        result = []
        for _ in range(count):
            data = self._read_decrypted(offset, 0x100)
            offset += 0x100
            result.append(self._read_null_string(data))
        return result

    def _parse_ssize(self) -> int:
        """Odpowiednik dumpSsize."""
        return self._get_int32_header(0x18)

    def _parse_tables(self) -> list[Table]:
        """Odpowiednik dumpTables — czyta sekcje TBEG/TEND z danymi."""
        table_offset = self._get_int32_header(0x84)
        table_count_data = self._read_decrypted(table_offset, 4)
        table_count = struct.unpack("<I", table_count_data)[0]
        offset = table_offset + 4

        tables = []
        for _ in range(table_count):
            entry = self._read_decrypted(offset, 0x50)
            offset += 0x50

            name = self._read_null_string(entry[:0x40])
            col_offset = struct.unpack_from("<I", entry, 0x40)[0]
            col_count  = struct.unpack_from("<I", entry, 0x48)[0]
            row_count  = struct.unpack_from("<I", entry, 0x4C)[0]

            # Czytanie nagłówków kolumn
            col_ptr = col_offset
            columns = []
            for _ in range(col_count):
                col_name = bytearray()
                for _ in range(1024):
                    b = self._read_decrypted(col_ptr, 1)[0]
                    col_ptr += 1
                    if b == 0:
                        break
                    col_name.append(b)
                columns.append(col_name.decode("latin-1", errors="replace"))

            # Czytanie wierszy
            rows = []
            for _ in range(row_count):
                row_values = []
                for _ in range(col_count):
                    cell = bytearray()
                    for _ in range(1024):
                        b = self._read_decrypted(col_ptr, 1)[0]
                        col_ptr += 1
                        if b == 0:
                            break
                        cell.append(b)
                    row_values.append(cell.decode("latin-1", errors="replace"))
                rows.append(TableRow(values=row_values))

            tables.append(Table(name=name, columns=columns, rows=rows))

        return tables

    def _parse_jobs(self, comments: dict[str, list[str]]) -> list[Job]:
        """Odpowiednik dumpJobs — czyta listę jobów z nazwami i adresami."""
        job_list_offset = self._get_int32_header(0x88)
        num_jobs = self._read_int32_raw(job_list_offset)
        offset = job_list_offset + 4

        jobs = []
        for _ in range(num_jobs):
            entry = self._read_decrypted(offset, 0x44)
            offset += 0x44

            name = self._read_null_string(entry[:0x40])
            address = struct.unpack_from("<i", entry, 0x40)[0]
            job_comments = comments.get(name, [])

            disassembly = []
            try:
                disassembly = self._disassemble_job(address)
            except Exception as e:
                disassembly = [f"; BŁĄD DISASSEMBLY: {e}"]

            jobs.append(Job(
                name=name,
                address=address,
                comments=job_comments,
                disassembly=disassembly,
            ))

        return jobs

    # --- Disassembler ---

    def _read_op_arg(self, offset: int, mode: int) -> tuple[str, int]:
        """
        Czyta argument operandu zgodnie z trybem adresowania.
        Zwraca (string_reprezentacja, nowy_offset).
        """
        if mode == 0:  # None
            return "", offset

        if mode in (1, 2, 3, 4):  # RegS/RegAB/RegI/RegL
            b = self._read_decrypted(offset, 1)[0]
            name = OA_MAP.get(b, f"?{b:02X}")
            return name, offset + 1

        if mode == 5:  # Imm8
            b = self._read_decrypted(offset, 1)[0]
            if b in (9, 10, 13) or 32 <= b < 127:
                ch = {9: r"\t", 10: r"\n", 13: r"\r"}.get(b, chr(b))
                return f"#'{ch}'", offset + 1
            return f"#${b:02X}.B", offset + 1

        if mode == 6:  # Imm16
            data = self._read_decrypted(offset, 2)
            val = struct.unpack("<h", data)[0]
            return f"#${val:04X}.I", offset + 2

        if mode == 7:  # Imm32
            data = self._read_decrypted(offset, 4)
            val = struct.unpack("<i", data)[0]
            return f"#${val:08X}.L", offset + 4

        if mode == 8:  # ImmStr
            data = self._read_decrypted(offset, 2)
            slen = struct.unpack("<h", data)[0]
            offset += 2
            if slen > 0:
                s_data = self._read_decrypted(offset, slen)
                offset += slen
                printable = all(
                    b in (9, 10, 13) or 32 <= b < 127
                    for b in s_data[:-1]
                )
                if printable and s_data[-1] == 0:
                    return f'"{s_data[:-1].decode("latin-1")}"', offset
                else:
                    hex_str = ",".join(f"${b:02X}.B" for b in s_data)
                    return "{" + hex_str + "}", offset
            return '""', offset

        if mode == 9:  # IdxImm
            data = self._read_decrypted(offset, 3)
            reg = data[0]
            idx = struct.unpack_from("<h", data, 1)[0]
            name = OA_MAP.get(reg, f"?{reg:02X}")
            return f"{name}[#${idx:04X}]", offset + 3

        if mode == 10:  # IdxReg
            data = self._read_decrypted(offset, 2)
            r0, r1 = data[0], data[1]
            n0 = OA_MAP.get(r0, f"?{r0:02X}")
            n1 = OA_MAP.get(r1, f"?{r1:02X}")
            return f"{n0}[{n1}]", offset + 2

        if mode == 11:  # IdxRegImm
            data = self._read_decrypted(offset, 4)
            r0, r1 = data[0], data[1]
            inc = struct.unpack_from("<h", data, 2)[0]
            n0 = OA_MAP.get(r0, f"?{r0:02X}")
            n1 = OA_MAP.get(r1, f"?{r1:02X}")
            return f"{n0}[{n1},#${inc:04X}]", offset + 4

        if mode == 12:  # IdxImmLenImm
            data = self._read_decrypted(offset, 5)
            reg = data[0]
            idx = struct.unpack_from("<h", data, 1)[0]
            length = struct.unpack_from("<h", data, 3)[0]
            name = OA_MAP.get(reg, f"?{reg:02X}")
            return f"{name}[#${idx:04X}]#${length:04X}", offset + 5

        if mode == 13:  # IdxImmLenReg
            data = self._read_decrypted(offset, 4)
            reg = data[0]
            idx = struct.unpack_from("<h", data, 1)[0]
            reg_len = data[3]
            name = OA_MAP.get(reg, f"?{reg:02X}")
            n_len = OA_MAP.get(reg_len, f"?{reg_len:02X}")
            return f"{name}[#${idx:04X}]{n_len}", offset + 4

        if mode == 14:  # IdxRegLenImm
            data = self._read_decrypted(offset, 4)
            reg, reg_idx = data[0], data[1]
            length = struct.unpack_from("<h", data, 2)[0]
            name = OA_MAP.get(reg, f"?{reg:02X}")
            n_idx = OA_MAP.get(reg_idx, f"?{reg_idx:02X}")
            return f"{name}[{n_idx}]#${length:04X}", offset + 4

        if mode == 15:  # IdxRegLenReg
            data = self._read_decrypted(offset, 3)
            reg, reg_idx, reg_len = data[0], data[1], data[2]
            name = OA_MAP.get(reg, f"?{reg:02X}")
            n_idx = OA_MAP.get(reg_idx, f"?{reg_idx:02X}")
            n_len = OA_MAP.get(reg_len, f"?{reg_len:02X}")
            return f"{name}[{n_idx}]{n_len}", offset + 3

        raise ValueError(f"Nieznany tryb adresowania: {mode}")

    def _disassemble_job(self, job_address: int) -> list[str]:
        """Odpowiednik disassembleJob — disassembluje bytecode BEST/1 joba."""
        offset = job_address
        found_first_eoj = False
        lines: dict[int, str] = {}
        label_set: set[int] = set()

        while True:
            address = offset
            header = self._read_decrypted(offset, 2)
            offset += 2

            op_code_val = header[0]
            op_addr_byte = header[1]
            mode0 = (op_addr_byte & 0xF0) >> 4
            mode1 = (op_addr_byte & 0x0F)

            if op_code_val not in OC_MAP:
                raise ValueError(f"Nieznany opcode: 0x{op_code_val:02X} @ 0x{address:08X}")

            mnemonic, arg0_is_near = OC_MAP[op_code_val]

            arg0, offset = self._read_op_arg(offset, mode0)
            arg1, offset = self._read_op_arg(offset, mode1)

            # Jeśli arg0 jest near address i tryb to Imm32 — zamień na etykietę
            if arg0_is_near and mode0 == 7:  # Imm32
                raw_val = int(arg0[2:-2], 16)  # wyciągnij hex z "#$XXXXXXXX.L"
                label_address = offset + raw_val
                label_set.add(label_address)
                arg0 = f"__{label_address:08X}"

            # Buduj linię
            if arg0:
                if arg1:
                    line = f"{mnemonic:<10} {arg0},{arg1}"
                else:
                    line = f"{mnemonic:<10} {arg0}"
            else:
                line = mnemonic

            lines[address] = line

            # eoj kończy job (dwa eoj z rzędu = koniec)
            if op_code_val == 0x1D:
                if found_first_eoj:
                    break
                found_first_eoj = True
            else:
                found_first_eoj = False

        # Buduj output z etykietami
        result = []
        for addr in sorted(lines):
            if addr in label_set:
                result.append(f"__{addr:08X}: {lines[addr]}")
            else:
                result.append(f"                    {lines[addr]}")

        return result

    # --- Główna metoda ---

    def parse(self) -> PrgFile:
        """Parsuje plik .prg i zwraca strukturę PrgFile."""
        info = self._parse_info()
        comments = self._parse_description()
        uses = self._parse_uses()
        ssize = self._parse_ssize()
        tables = self._parse_tables()
        jobs = self._parse_jobs(comments)

        return PrgFile(
            info=info,
            uses=uses,
            ssize=ssize,
            tables=tables,
            jobs=jobs,
        )


# ---------------------------------------------------------------------------
# Publiczne API

def parse_prg(filepath: str) -> PrgFile:
    """
    Parsuje plik BMW EDIABAS .prg i zwraca PrgFile z metadanymi,
    listą jobów, tabelami i komentarzami.

    Przykład użycia:
        prg = parse_prg("ms43ds0.prg")
        for job in prg.jobs:
            print(job.name)
    """
    return PrgParser(filepath).parse()


# ---------------------------------------------------------------------------
# CLI — uruchomienie z linii komend

if __name__ == "__main__":
    import sys
    import json

    if len(sys.argv) < 2:
        print("Użycie: python prg_parser.py <plik.prg>")
        sys.exit(1)

    prg = parse_prg(sys.argv[1])

    print(f"=== {Path(sys.argv[1]).name} ===")
    print(f"Wersja BIP:    {prg.info.bip_version}")
    print(f"Rewizja:       {prg.info.revision}")
    print(f"Autor:         {prg.info.author}")
    print(f"Ostatnia zmiana: {prg.info.last_changed}")
    print(f"Uses:          {', '.join(prg.uses)}")
    print(f"Tabele:        {len(prg.tables)}")
    print(f"Joby ({len(prg.jobs)}):")
    for job in prg.jobs:
        comment_preview = job.comments[0] if job.comments else ""
        print(f"  - {job.name:<40} @ 0x{job.address:08X}  {comment_preview}")
    prg = parse_prg(sys.argv[1])